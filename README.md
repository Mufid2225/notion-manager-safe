# Notion Manager Safe

[English](README.md) · [Bahasa Indonesia](README.id.md)

A safety-first AI agent skill for documenting and managing Notion workspace content through Notion's official REST API.

> This is an independent community skill, not an official Notion product. API requests run locally with the user's own credentials; this repository does not provide a hosted service.

> **API and policy note:** REST is the primary transport for this skill. Notion officially documents its REST API for scripts and integrations. Requests require a bearer token and `Notion-Version` header, and can only access content permitted to that credential. Follow workspace controls, rate limits, credential security, and Notion's terms. MCP is an optional alternative when the user chooses it; this skill does not silently switch transports.

## What it does

- Captures and organizes general notes, records, decisions, research, meeting summaries, and project documentation in Notion.
- Finds the intended page or data source by title through the API, confirms its parent and schema where applicable, and checks existing content before writing.
- Builds a draft from user-provided details and relevant evidence, shows the exact target and payload, and waits for approval.
- Creates or updates a page through documented REST endpoints, then reads it back and reports its Notion URL.
- Works directly with Notion pages and data sources; no other workspace product is required.

## How it works

The skill uses HTTPS requests to `https://api.notion.com/v1`. It does not scrape the Notion website or call undocumented endpoints.

1. Authenticate with a Notion personal access token (PAT) for a personal/local workflow, or use a properly registered OAuth connection for a multi-user integration.
2. Search for the requested page or data source by title with `POST /v1/search`.
3. Confirm the exact result and parent. For a data source, resolve its ID and current property schema. Do not trust a remembered ID by itself.
4. Check the target for existing content before creating a page or record. Query a data source for records; inspect a parent page's content when adding a note there.
5. Prepare a draft and API payload that match the live schema. Show the target, fields, and exact values to the user.
6. Wait for explicit approval, then call `POST /v1/pages` to create or `PATCH /v1/pages/{page_id}` to update.
7. Read the page back and query the data source again. If the outcome is unclear, verify before retrying so a timeout does not create a duplicate.

The API uses separate database and data source IDs in current versions. Search can return pages or data sources; `GET /v1/data_sources/{data_source_id}` provides the schema for structured records. A standalone note can instead be created as a child of a verified page. See the [official API reference](https://developers.notion.com/reference/intro) and [data source guide](https://developers.notion.com/guides/data-apis/working-with-databases).

## Safety model

- Use only documented Notion REST endpoints and the required `Notion-Version` header. The version shown in the examples is the current version documented when this README was reviewed; check Notion's versioning page before changing it.
- Resolve the requested page or data source live by title. If results are ambiguous, ask which one to use. Never infer the target from an old ID or workspace URL alone.
- For structured records, inspect the parent database and exact property names/types before building a payload. Do not create databases, properties, or templates automatically.
- Check for duplicates before creating records. Use pagination where needed; do not assume the first response contains all matching rows.
- Ask for explicit approval before each create, update, or archive operation. Bulk changes require separate approval for exact scope and count.
- Do not permanently delete content. Do not retry a write until checking whether the first request succeeded.
- Keep PATs and OAuth secrets out of chat, source files, command arguments, logs, and Git. Use a process environment or secret manager, least privilege, and only share the required content with the connection.
- Read back every mutation and report the destination URL and what was verified.

## Pagination and API errors

Data-source queries are cursor-paginated. Set `page_size` to at most `100`. Append each response's `results`; while `has_more` is `true`, send another `POST /v1/data_sources/{data_source_id}/query` with `start_cursor` set to that response's `next_cursor`. Stop only when `has_more` is `false`. A short page is not proof that the query is complete. Notion caps a query at 10,000 results; check every response for `request_status.type = "incomplete"` and narrow or partition a query that reaches the cap.

First-page request:

```sh
curl -X POST 'https://api.notion.com/v1/data_sources/<verified_data_source_id>/query' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data '{"page_size":100}'
```

If the response has `has_more: true`, use its `next_cursor` in the next request:

```sh
curl -X POST 'https://api.notion.com/v1/data_sources/<verified_data_source_id>/query' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data '{"page_size":100,"start_cursor":"<next_cursor_from_previous_response>"}'
```

| HTTP | Meaning | Safe next step |
|---|---|---|
| `400` | Invalid request or schema validation error | Read the response `code` and `message`; correct the endpoint, version header, property name/type, or body. Do not retry the same payload unchanged. |
| `401` | Missing or invalid bearer token | Check that the local credential is configured and belongs to the intended integration. Never print it. |
| `403` | Credential lacks permission or the operation is restricted | Verify the resource is shared with the connection and the requested action is allowed. Do not broaden permissions automatically. |
| `404` | Resource ID is wrong, unavailable, or not shared with this credential | Search by title again and re-verify the parent and ID. Do not create a replacement until confirming the original target is not accessible. |
| `409` | Conflict while saving | Read current state, refresh stale values, and resolve the conflict before another write. |
| `429` | Rate limit | Honor `Retry-After` when present and use bounded backoff. Do not fire parallel retries. |
| `500`, `502`, `503`, `504`, `529` | Server/network failure, timeout, or overload | Respect `Retry-After` or `additional_data.retry_guidance` when present. A write may have succeeded despite a timeout, so read/query for the intended change before retrying. |

For an unclear write result, reconcile by reading the target page and querying for the intended record before any retry. Do not assume a failed response means the mutation failed.

## Authentication setup

For a personal/local workflow, create a PAT in Notion's [Developer portal](https://www.notion.so/developers/tokens), enable the **Notion API** capability, and select the intended workspace. Workspace admins may restrict PAT creation. A PAT acts with its creator's permissions. For an integration used by multiple people, use Notion's OAuth flow instead of sharing one person's PAT.

Store the token in `NOTION_API_KEY` in the environment of the process that runs the agent. Do not paste it into chat, put it in a project `.env` file that could be committed, or pass it as a command-line argument. Notion permissions still apply; an inaccessible resource may need to be shared with the connection or opened to the PAT owner.

Set it for the current terminal session only. The examples read the token without echoing it; run the agent from the same terminal so it inherits the variable.

**PowerShell (Windows):**

```powershell
$secureToken = Read-Host 'Notion API token' -AsSecureString
$tokenPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $env:NOTION_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPtr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPtr)
    $secureToken.Dispose()
    Remove-Variable secureToken, tokenPtr
}
```

**macOS/Linux (Bash or compatible shell):**

```sh
read -r -s -p 'Notion API token: ' NOTION_API_KEY
printf '\n'
export NOTION_API_KEY
```

Environment variables are available to child processes running as your user. Use a trusted personal device, do not enable verbose request logging, and prefer your agent's supported secret manager when available. If you start the agent from a desktop launcher, configure the variable through that client's secure environment mechanism; a terminal variable will not automatically reach an already-running app.

Every request needs these headers:

```http
Authorization: Bearer <token from NOTION_API_KEY>
Notion-Version: 2026-03-11
Content-Type: application/json
```

Do not copy the placeholder as a real credential. See [Notion's credential security guide](https://developers.notion.com/guides/authorization/credential-security).

## Example: discover a data source

Use the exact or distinctive database title supplied by the user. This read-only request searches only data sources the credential can access:

```sh
curl -X POST 'https://api.notion.com/v1/search' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data '{"query":"Project Notes","filter":{"property":"object","value":"data_source"}}'
```

The same read-only search from PowerShell uses `Invoke-RestMethod`:

```powershell
$headers = @{
    Authorization = "Bearer $env:NOTION_API_KEY"
    "Notion-Version" = "2026-03-11"
}
$body = @{
    query = "Project Notes"
    filter = @{ property = "object"; value = "data_source" }
} | ConvertTo-Json -Depth 5

$result = Invoke-RestMethod -Method Post `
    -Uri "https://api.notion.com/v1/search" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body
```

Keep the result scoped to the intended workspace. Do not print authorization headers or tokens while debugging.

Inspect the returned title, parent database, data source ID, and properties. If multiple results could match, ask before proceeding. Use the returned `data_source_id` to retrieve the schema or query its rows; do not copy an example ID or assume the database ID is also the data source ID. For a standalone page, search with `filter` set to `object = page` and verify the page ID and parent instead.

## Example: create and update payloads

These JSON bodies are templates, not ready-to-send requests. Replace every placeholder with the verified data source ID, property name, property type, and allowed option from the live schema. Include only properties that exist and that the user approved.

Create a structured record in a data source with `POST /v1/pages`:

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
    },
    "<exact_number_property_name>": {
      "number": 12
    },
    "<exact_url_property_name>": {
      "url": "<approved related URL>"
    }
  }
}
```

For a standalone note under an existing page, use the verified page as the parent and send page content as Markdown instead of data-source properties:

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

Use only a parent the user intended. If the user asks to add content inside an existing page rather than create a child page, use the documented block content endpoint and verify the resulting blocks.

For an update, call `PATCH /v1/pages/{verified_page_id}` and send only the properties the user approved to change. Omitted properties keep their current values:

```json
{
  "properties": {
    "<exact_rich_text_property_name>": {
      "rich_text": [{ "text": { "content": "<approved replacement text>" } }]
    }
  }
}
```

Property names, data types, and select options must come from the target data source's live schema. A property typed `status`, for example, needs its own schema-matching value shape; do not assume it is a `select` or `rich_text` property. After writing, retrieve the returned page and verify the changed properties.

### Complete REST requests

These examples include endpoint, headers, and body. Replace all placeholders using the live data-source schema and the values the user approved. They are examples only; do not execute a write before showing the exact target and payload and receiving approval.

Create a record page:

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
      "rich_text": [{ "text": { "content": "<approved text>" } }]
    }
  }
}
JSON
```

Update only the approved property on an existing page:

```sh
curl -X PATCH 'https://api.notion.com/v1/pages/<verified_page_id>' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H 'Notion-Version: 2026-03-11' \
  -H 'Content-Type: application/json' \
  --data-binary @- <<'JSON'
{
  "properties": {
    "<exact_rich_text_property_name>": {
      "rich_text": [{ "text": { "content": "<approved replacement text>" } }]
    }
  }
}
JSON
```

The property names and value shapes above are illustrative. Copy names and types from the verified schema; include only fields approved for the operation. Keep the token in the process environment, never substitute its literal value into the command.

Equivalent complete create request in PowerShell:

```powershell
$headers = @{
    Authorization = "Bearer $env:NOTION_API_KEY"
    "Notion-Version" = "2026-03-11"
}
$createBody = @{
    parent = @{
        type = "data_source_id"
        data_source_id = "<verified_data_source_id>"
    }
    properties = @{
        "<exact_title_property_name>" = @{
            title = @(@{ text = @{ content = "<approved title>" } })
        }
        "<exact_rich_text_property_name>" = @{
            rich_text = @(@{ text = @{ content = "<approved text>" } })
        }
    }
} | ConvertTo-Json -Depth 10

$created = Invoke-RestMethod -Method Post `
    -Uri "https://api.notion.com/v1/pages" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $createBody
$created.url
```

Equivalent update request; send only the approved changed property:

```powershell
$updateBody = @{
    properties = @{
        "<exact_rich_text_property_name>" = @{
            rich_text = @(@{ text = @{ content = "<approved replacement text>" } })
        }
    }
} | ConvertTo-Json -Depth 10

$updated = Invoke-RestMethod -Method Patch `
    -Uri "https://api.notion.com/v1/pages/<verified_page_id>" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $updateBody
$updated.url
```

## Example interaction

```text
User: Save today's decision in the project notes database.

Agent: The REST search found one matching “Project Notes” data source. I
checked its parent and schema, then searched for an existing record with the
same title. I drafted a new record with the decision summary and date. Do you
approve these exact values?

User: Yes, create it.

Agent: The page was created through the Notion API, then read back. Here is its
URL: <Notion URL>
```

The example uses fictional workspace content. Resolve the live destination and schema and get approval before writing.

## Optional MCP transport

Notion also offers an official remote MCP server at `https://mcp.notion.com/mcp`. REST remains the default. Use MCP only if REST is unavailable, fails authentication/connectivity, cannot safely handle the needed operation, or the user explicitly requests MCP. Do not silently switch transports; report the fallback and reconcile state before retrying a write.

This repository currently provides the agent instructions and request examples; it does not include a REST helper or CLI. A helper can be added separately for repeatable request handling without changing the skill's rules for target discovery, schema checks, approval, and verification.

## Install as an agent skill

Clone this repository, then copy `SKILL.md` and `agents/` into the skill directory used by your client:

| Agent | Personal skill directory |
|---|---|
| Codex | `~/.agents/skills/notion-manager-safe/` |
| Claude Code | `~/.claude/skills/notion-manager-safe/` |
| OpenCode | `~/.config/opencode/skills/notion-manager-safe/` |

Skill discovery and paths can change; check your agent's current documentation if it does not load the skill. Installing the skill does not create a PAT or grant workspace access.

## Repository files

| Path | Purpose |
|---|---|
| `SKILL.md` | Agent instructions and REST workflow |
| `agents/openai.yaml` | Optional agent interface metadata |
| `README.md` | English documentation |
| `README.id.md` | Indonesian documentation |
| `LICENSE` | MIT license for this repository's materials |
| `SECURITY.md` | Private vulnerability reporting guidance |

## Official references

- [Notion API introduction](https://developers.notion.com/reference/intro)
- [Notion API quickstart](https://developers.notion.com/guides/notion-api/quick-start)
- [Search by title](https://developers.notion.com/reference/post-search)
- [Retrieve a data source](https://developers.notion.com/reference/retrieve-a-data-source)
- [Query a data source](https://developers.notion.com/reference/query-a-data-source)
- [Pagination](https://developers.notion.com/reference/pagination)
- [Create a page](https://developers.notion.com/reference/post-page)
- [Update a page](https://developers.notion.com/reference/patch-page)
- [API errors](https://developers.notion.com/reference/errors)
- [Request limits](https://developers.notion.com/reference/request-limits)
- [Authorization overview](https://developers.notion.com/guides/authorization/overview)
- [Personal access tokens](https://developers.notion.com/guides/connections-and-tokens/personal-access-tokens)
- [Secure API credentials](https://developers.notion.com/guides/authorization/credential-security)
- [Notion API versioning](https://developers.notion.com/reference/versioning)
- [Notion Terms of Service](https://www.notion.so/terms)

## License and security

This repository's materials are licensed under [MIT](LICENSE). Notion and workspace content remain subject to Notion's terms and the workspace owner's controls. Report security issues privately through GitHub's **Report a vulnerability** feature; do not include credentials or private workspace content. See [SECURITY.md](SECURITY.md).
