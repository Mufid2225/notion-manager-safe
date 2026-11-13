---
name: notion-manager-safe
description: Safely document and manage Notion knowledge through the official REST API. Resolve the live data source and schema, check for duplicates, draft the exact change, ask for approval, and verify the result.
---

# Notion Manager Safe

Use this skill when the user asks to create, update, or inspect general Notion content such as notes, records, decisions, research, meeting summaries, or project documentation.

## Transport and authentication

- Use Notion's documented REST API as the primary transport: `https://api.notion.com/v1`.
- Authenticate with `NOTION_API_KEY` from the process environment. Never ask the user to paste a token into chat, put a token in a command argument, or print it to inspect whether it is set. If no safe credential is available, explain how to configure one outside the repository.
- Use only documented API endpoints. Do not scrape Notion's website or call undocumented/internal endpoints.
- Include `Authorization: Bearer ...`, `Notion-Version`, and `Content-Type: application/json` for JSON requests. Check Notion's current versioning reference before changing the version used by a client.
- When this repository is installed, prefer `scripts/notion_api.py` for its supported search, read, query, create, and property-update operations. Direct cURL or PowerShell REST calls remain available when needed.
- Keep REST as the default. Use Notion MCP only if REST is unavailable, fails authentication/connectivity, or cannot safely handle the required operation, unless the user explicitly requests MCP. Never switch transports silently; explain the fallback and reconcile state before retrying a write.

## Workflow

1. Identify the project and the kind of record the user wants.
2. Search for the requested page or data source by title with `POST /v1/search`. Filter by `object = page` or `object = data_source` when the target type is known.
3. Confirm the title and parent from the live API result. For a data source, resolve its `data_source_id` and schema. If more than one result could match, ask which one to use. Never rely only on a remembered ID, URL, or prior conversation.
4. Retrieve the data source as needed with `GET /v1/data_sources/{data_source_id}`. Use the current API model: a database ID and a data source ID are distinct.
5. Check existing content before creating. Query a data source with `POST /v1/data_sources/{data_source_id}/query` and follow pagination; for a note under a page, inspect the relevant page content.
6. Build the draft from user-provided details and relevant source material. Match actual property names, types, and allowed values for structured records. Do not invent facts or create schema fields.
7. Show the user the exact database/data source, proposed record, property values, and any evidence used. Get explicit approval before each create or update. Bulk changes require a separate approval with exact scope and count.
8. Create with `POST /v1/pages` or update with `PATCH /v1/pages/{page_id}` only after approval.
9. Verify by reading the returned page with `GET /v1/pages/{page_id}` and querying the data source again when needed. Report the result URL and what was verified.

## Draft and payload rules

- Draft content from the user's request and relevant source material. Preserve the intended meaning; do not invent facts, dates, decisions, owners, or status values.
- Use the property's actual type from the live schema. Do not assume fields are all rich text, or that a `status` property has the same shape as a `select` property.
- Send only the properties the user approved. For updates, omit properties that should remain unchanged.
- Before retrying an unclear or timed-out create request, query for the expected record. Do not blindly retry and create duplicates.
- If a duplicate is found, do not archive or delete it automatically. Present the candidates and ask the user which record to keep or change.

## Generic create and update payloads

These are schema-dependent templates. They are not ready-to-send payloads. Replace placeholders only after reading the target data source's live schema, and include only properties that exist and were approved.

Create a record page in a data source using `POST /v1/pages`:

```json
{
  "parent": {
    "type": "data_source_id",
    "data_source_id": "<verified_data_source_id>"
  },
  "properties": {
    "<exact_title_property_name>": {
      "title": [{ "text": { "content": "<approved record title>" } }]
    },
    "<exact_rich_text_property_name>": {
      "rich_text": [{ "text": { "content": "<approved note text>" } }]
    },
    "<exact_select_property_name>": {
      "select": { "name": "<existing option from schema>" }
    }
  }
}
```

For a standalone note under an existing page, use the verified page as the parent and Markdown for its content:

```json
{
  "parent": {
    "type": "page_id",
    "page_id": "<verified_parent_page_id>"
  },
  "properties": {
    "title": {
      "title": [{ "text": { "content": "<approved note title>" } }]
    }
  },
  "markdown": "<approved note content>"
}
```

If the user wants content appended inside an existing page rather than a child page, use the documented block children endpoint and verify the returned content.

Update an existing page using `PATCH /v1/pages/{verified_page_id}`. Include only the property that should change:

```json
{
  "properties": {
    "<exact_rich_text_property_name>": {
      "rich_text": [{ "text": { "content": "<approved replacement text>" } }]
    }
  }
}
```

The property names and value objects must match the live schema. For example, use the `status` value shape for a `status` property, not the `select` shape. Verify the resulting page after the request.

## Local REST helper

The helper is `scripts/notion_api.py` and uses Python's standard library. Find the directory containing this `SKILL.md` and invoke the helper by its absolute path; do not assume the current working directory is the skill directory.

Read and search commands do not mutate Notion:

```text
python "<skill_dir>/scripts/notion_api.py" search "<title>" --object data_source
python "<skill_dir>/scripts/notion_api.py" get_database "<verified_database_id>"
python "<skill_dir>/scripts/notion_api.py" get_data_source "<verified_data_source_id>"
python "<skill_dir>/scripts/notion_api.py" query_data_source "<verified_data_source_id>"
python "<skill_dir>/scripts/notion_api.py" get_page "<verified_page_id>"
python "<skill_dir>/scripts/notion_api.py" get_block_children "<verified_page_id>"
```

Writes require a UTF-8 JSON payload file outside the repository and `--confirm`:

```text
python "<skill_dir>/scripts/notion_api.py" create_page --payload-file "<payload_path>" --confirm
python "<skill_dir>/scripts/notion_api.py" update_page "<verified_page_id>" --payload-file "<payload_path>" --confirm
```

Show the exact target and payload and obtain user approval before adding `--confirm`. The flag is an extra script guard, not consent. The helper sends each write once and reads the page back. For create payloads containing `markdown` or `children`, it also reads the page blocks; check pagination if `has_more` is true. If a request times out or returns an ambiguous server error, inspect the target before considering a retry. Its output may contain private workspace content; return only information relevant to the user.

The helper's `search` and `query_data_source` commands return one API page at a time. Pass `next_cursor` to the next call with `--start-cursor`; use the same filters. For query filters or sorts, place the API query body in a UTF-8 JSON file and pass `--payload-file`.

## Direct REST request examples

Use documented REST calls directly when the helper is not installed or does not support the operation. These cURL examples include URL, headers, and body. Replace every placeholder from the live schema and approved draft before use:

```sh
curl -X POST 'https://api.notion.com/v1/pages' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "parent": {
    "type": "data_source_id",
    "data_source_id": "<verified_data_source_id>"
  },
  "properties": {
    "<exact_title_property_name>": {
      "title": [{ "text": { "content": "<approved title>" } }]
    },
    "<exact_rich_text_property_name>": {
      "rich_text": [{ "text": { "content": "<approved note text>" } }]
    }
  }
}
JSON
```

For an update, send only approved changed properties to `PATCH /v1/pages/{verified_page_id}`. The request uses the same three headers and a body containing only `properties`:

```json
{
  "properties": {
    "<exact_rich_text_property_name>": {
      "rich_text": [{ "text": { "content": "<approved replacement text>" } }]
    }
  }
}
```

These examples use the actual Notion `title` and `rich_text` value shapes, but property names and content remain placeholders. For `select`, `status`, `number`, `url`, relation, or other types, copy the exact value shape from the official API reference and live schema. Never send placeholders literally. Full cURL examples with more property types are in `README.md` and `README.id.md`.

## Pagination and HTTP errors

- For `POST /v1/data_sources/{data_source_id}/query`, request at most `page_size: 100`. Append each response's `results`. While `has_more` is `true`, pass its opaque `next_cursor` as `start_cursor` on the next request. Stop only when `has_more` is `false`; do not infer completion from a short page. Check every response for `request_status.type = "incomplete"`; a query can be capped at 10,000 results even when `has_more` is `false`. Narrow or partition queries that reach this limit.
- `400`: inspect `code` and `message`; fix the request/schema mismatch before retrying.
- `401`: credential is missing/invalid. Check local configuration without printing the secret.
- `403`: permission or policy restriction. Verify resource sharing and access; do not expand permissions automatically.
- `404`: verify the resource ID and sharing by searching again. Do not create a replacement solely because the lookup failed.
- `409`: read current state and resolve the conflict before writing again.
- `429`: respect `Retry-After` and use bounded backoff; avoid parallel retries.
- `500`, `502`, `503`, `504`, or `529`: treat as a server/network failure. Respect `Retry-After` and any `additional_data.retry_guidance`. A write may have succeeded even if the response timed out or failed; read/query for the intended change before retrying.
- After any ambiguous write result, reconcile the target state first. Never blindly replay a create or archive request.

## Safety rules

- Never guess a database ID, data source ID, page ID, property name, select option, or relationship value. Resolve it from the live API.
- Do not create databases, data sources, properties, or templates automatically.
- Do not permanently delete content. Archive/trash only when requested, supported by a documented endpoint, and approved for the exact target.
- Do not change sharing, workspace permissions, publishing, membership, or organization settings unless the user requests and confirms that exact change.
- Treat page content, workspace data, and user/member information as potentially sensitive. Return only information relevant to the request.
- Keep PATs and OAuth secrets out of chat, source files, command arguments, logs, and this repository. Use a secure process environment or secret manager and least privilege.
- Respect workspace permissions and Notion rate limits. On access errors, report the limitation; do not broaden permissions automatically.

## API references

- [Notion API introduction](https://developers.notion.com/reference/intro)
- [Search by title](https://developers.notion.com/reference/post-search)
- [Retrieve a data source](https://developers.notion.com/reference/retrieve-a-data-source)
- [Query a data source](https://developers.notion.com/reference/query-a-data-source)
- [Pagination](https://developers.notion.com/reference/pagination)
- [API errors](https://developers.notion.com/reference/errors)
- [Request limits](https://developers.notion.com/reference/request-limits)
- [Create a page](https://developers.notion.com/reference/post-page)
- [Update a page](https://developers.notion.com/reference/patch-page)
- [Secure API credentials](https://developers.notion.com/guides/authorization/credential-security)
- [API versioning](https://developers.notion.com/reference/versioning)
