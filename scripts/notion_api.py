#!/usr/bin/env python3
"""Guarded local helper for Notion's documented REST API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
TIMEOUT_SECONDS = 30


class NotionApiError(RuntimeError):
    """An API or input error with safe-to-display detail."""


class NotionClient:
    def __init__(self) -> None:
        token = os.environ.get("NOTION_API_KEY")
        if not token:
            raise NotionApiError(
                "NOTION_API_KEY is not set in this process environment."
            )
        self._token = token

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> Any:
        method = method.upper()
        if method not in {"GET", "POST", "PATCH"}:
            raise NotionApiError("This helper only supports GET, POST, and PATCH.")

        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": NOTION_VERSION,
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"

        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        if params:
            url += "?" + urlencode(params)
        request = Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )
        is_write = (endpoint == "pages" and method == "POST") or (
            endpoint.startswith("pages/") and method == "PATCH"
        )
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read()
        except HTTPError as exc:
            code = ""
            try:
                error_body = json.loads(exc.read().decode("utf-8"))
                if isinstance(error_body, dict) and isinstance(error_body.get("code"), str):
                    code = f" ({error_body['code']})"
            except (UnicodeDecodeError, json.JSONDecodeError, OSError):
                pass
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            retry_note = f" Retry-After: {retry_after}s." if retry_after.isdigit() else ""
            ambiguous = (
                " The write outcome may be unclear; read the target before considering a retry."
                if is_write and exc.code in {500, 502, 503, 504, 529}
                else ""
            )
            raise NotionApiError(
                f"Notion API HTTP {exc.code}{code}.{retry_note}{ambiguous} Response details omitted."
            ) from None
        except (URLError, TimeoutError, OSError):
            ambiguous = (
                " The write outcome may be unclear; read the target before considering a retry."
                if is_write
                else ""
            )
            raise NotionApiError(
                f"Could not reach the Notion API.{ambiguous} Request details omitted."
            ) from None

        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise NotionApiError("The Notion API returned an invalid JSON response.") from None


def safe_id(value: str, label: str) -> str:
    if not value.strip():
        raise NotionApiError(f"{label} must not be empty.")
    return quote(value.strip(), safe="")


def read_payload(file_path: str) -> dict[str, Any]:
    try:
        payload_path = Path(file_path).expanduser().resolve()
        skill_repo = Path(__file__).resolve().parent.parent
        try:
            payload_path.relative_to(skill_repo)
        except ValueError:
            pass
        else:
            raise NotionApiError("Keep private payload files outside this repository.")
        value = json.loads(payload_path.read_text(encoding="utf-8"))
    except NotionApiError:
        raise
    except (OSError, json.JSONDecodeError):
        raise NotionApiError("Could not read a valid UTF-8 JSON payload file.") from None
    if not isinstance(value, dict):
        raise NotionApiError("The JSON payload must be an object.")
    return value


def require_confirmation(args: argparse.Namespace) -> None:
    if not args.confirm:
        raise NotionApiError(
            "Write blocked. Obtain approval for this exact change, then pass --confirm."
        )


def validate_create_payload(payload: dict[str, Any]) -> None:
    parent = payload.get("parent")
    if not isinstance(parent, dict):
        raise NotionApiError("Create payload must contain a verified parent object.")
    parent_type = parent.get("type")
    expected_key = (
        {"page_id": "page_id", "data_source_id": "data_source_id"}.get(parent_type)
        if isinstance(parent_type, str)
        else None
    )
    if not expected_key or not isinstance(parent.get(expected_key), str) or not parent[expected_key].strip():
        raise NotionApiError(
            "Create payload parent must use a verified page_id or data_source_id."
        )
    if not isinstance(payload.get("properties"), dict):
        raise NotionApiError("Create payload must contain a properties object.")
    if payload.get("allow_async") is True:
        raise NotionApiError(
            "Async page creation is not supported because this helper verifies the page immediately."
        )


def validate_update_payload(payload: dict[str, Any]) -> None:
    if set(payload) != {"properties"} or not isinstance(payload.get("properties"), dict):
        raise NotionApiError(
            "Update payload must contain only the approved properties object."
        )
    if not payload["properties"]:
        raise NotionApiError("Update payload properties must not be empty.")


def confirmed_write(client: NotionClient, args: argparse.Namespace) -> dict[str, Any]:
    require_confirmation(args)
    payload = read_payload(args.payload_file)
    expected_page_id = None

    if args.command == "create_page":
        validate_create_payload(payload)
        response = client.request("POST", "pages", payload=payload)
        action = "created"
    else:
        validate_update_payload(payload)
        expected_page_id = args.page_id.strip()
        page_id = safe_id(expected_page_id, "page_id")
        response = client.request(
            "PATCH", f"pages/{page_id}", payload=payload
        )
        action = "updated"

    page_id_value = response.get("id") if isinstance(response, dict) else None
    if not isinstance(page_id_value, str) or not page_id_value:
        raise NotionApiError(
            "The write returned without a page ID. Read the target state before retrying."
        )
    if expected_page_id and page_id_value.replace("-", "").lower() != expected_page_id.replace("-", "").lower():
        raise NotionApiError(
            "The update returned an unexpected page ID. Inspect both target states before retrying."
        )
    try:
        verified = client.request("GET", f"pages/{safe_id(page_id_value, 'page_id')}")
        verified_content = None
        if args.command == "create_page" and any(
            key in payload for key in ("children", "markdown")
        ):
            verified_content = client.request(
                "GET",
                f"blocks/{safe_id(page_id_value, 'page_id')}/children",
                params={"page_size": 100},
            )
    except NotionApiError as exc:
        raise NotionApiError(
            f"The page was {action}, but read-back verification failed. "
            "Do not retry the write; inspect the page state. "
            f"{exc}"
        ) from None
    result: dict[str, Any] = {"mutation": action, "verified_page": verified}
    if verified_content is not None:
        result["verified_content"] = verified_content
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Guarded Notion REST API helper")
    commands = root.add_subparsers(dest="command", required=True)

    search = commands.add_parser("search", help="Search pages or data sources by title")
    search.add_argument("query")
    search.add_argument("--object", choices=("page", "data_source"))
    search.add_argument("--page-size", type=int, default=100)
    search.add_argument("--start-cursor")

    for name, label in (
        ("get_page", "page_id"),
        ("get_database", "database_id"),
        ("get_data_source", "data_source_id"),
    ):
        item = commands.add_parser(name)
        item.add_argument(label)

    children = commands.add_parser("get_block_children")
    children.add_argument("block_id")
    children.add_argument("--page-size", type=int, default=100)
    children.add_argument("--start-cursor")

    query = commands.add_parser("query_data_source")
    query.add_argument("data_source_id")
    query.add_argument("--payload-file")
    query.add_argument("--page-size", type=int)
    query.add_argument("--start-cursor")

    for name in ("create_page", "update_page"):
        item = commands.add_parser(name)
        if name == "update_page":
            item.add_argument("page_id")
        item.add_argument("--payload-file", required=True)
        item.add_argument("--confirm", action="store_true")
    return root


def validate_page_size(value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100:
        raise NotionApiError("page_size must be an integer between 1 and 100.")


def execute(client: NotionClient, args: argparse.Namespace) -> Any:
    if args.command == "search":
        if not args.query.strip():
            raise NotionApiError("Search query must not be empty.")
        validate_page_size(args.page_size)
        payload: dict[str, Any] = {
            "query": args.query,
            "page_size": args.page_size,
        }
        if args.object:
            payload["filter"] = {"property": "object", "value": args.object}
        if args.start_cursor:
            payload["start_cursor"] = args.start_cursor
        return client.request("POST", "search", payload=payload)

    if args.command == "get_page":
        return client.request("GET", f"pages/{safe_id(args.page_id, 'page_id')}")
    if args.command == "get_database":
        return client.request("GET", f"databases/{safe_id(args.database_id, 'database_id')}")
    if args.command == "get_data_source":
        return client.request(
            "GET", f"data_sources/{safe_id(args.data_source_id, 'data_source_id')}"
        )
    if args.command == "get_block_children":
        validate_page_size(args.page_size)
        params: dict[str, str | int] = {"page_size": args.page_size}
        if args.start_cursor:
            params["start_cursor"] = args.start_cursor
        return client.request(
            "GET", f"blocks/{safe_id(args.block_id, 'block_id')}/children", params=params
        )
    if args.command == "query_data_source":
        payload = read_payload(args.payload_file) if args.payload_file else {}
        if args.page_size is not None:
            payload["page_size"] = args.page_size
        else:
            payload.setdefault("page_size", 100)
        validate_page_size(payload["page_size"])
        if args.start_cursor:
            payload["start_cursor"] = args.start_cursor
        return client.request(
            "POST",
            f"data_sources/{safe_id(args.data_source_id, 'data_source_id')}/query",
            payload=payload,
        )
    if args.command in {"create_page", "update_page"}:
        return confirmed_write(client, args)
    raise NotionApiError(f"Unsupported command: {args.command}")


def main() -> int:
    try:
        args = parser().parse_args()
        result = execute(NotionClient(), args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except NotionApiError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
