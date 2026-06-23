# Technical Requirements Document

## System Overview

A GitHub Action triggers a Python CLI on push to `main` when files matching `docs/**/*.md` change. The CLI converts changed Markdown files into Confluence Storage Format and creates or updates the corresponding Confluence page via the REST API v2.

---

## Functional Requirements

### FR-01: Trigger

- The GitHub Action triggers on `push` to the default branch with `paths: ["docs/**/*.md"]`.
- Only files that changed in the push are processed (not all managed files).
- Full re-sync must be triggerable manually via `workflow_dispatch`.

### FR-02: Page Mapping

- Page identity is determined by a checked-in YAML manifest (`confluence-manifest.yaml`).
- Each entry maps a file path to a Confluence `page_id`, `space_id`, `parent_id`, and `title`.
- The tool must refuse to publish a file that has no manifest entry (no implicit creation in Phase 1).
- Page IDs are used, not titles. Title lookups are not permitted as they break on renames.

### FR-03: Conversion

- Markdown is parsed into an AST using `mistletoe`.
- A custom `mistletoe` renderer converts the AST to Confluence Storage Format (XHTML-based).
- Supported syntax in Phase 1:
  - Headings (H1-H6)
  - Paragraphs and line breaks
  - Bold, italic, inline code
  - Ordered and unordered lists
  - Fenced code blocks with language labels
  - Blockquotes
  - Horizontal rules
  - Hyperlinks (external URLs)
- The build must fail on any unsupported syntax node encountered during conversion.
- No silent fallbacks. Unsupported nodes raise a `ConversionError` with the source file and line.

### FR-04: Publishing

- Before updating, retrieve the current page version from the Confluence API.
- Submit `version.number + 1` in the update payload.
- Store the Git commit SHA in the `version.message` field.
- Add a machine-readable banner at the top of every published page:

  ```
  This page is generated from GitHub. Manual edits will be overwritten.
  Source: <repo>/<path> @ <commit-sha>
  ```

### FR-05: Change Detection

- Compute a hash of the rendered Confluence Storage Format content before publishing.
- Retrieve the current page content hash from Confluence.
- Skip the API update if hashes match (no content change).
- Log skipped pages.

### FR-06: Edit Conflict Detection

- On each update, compare the page's last-modified version with the version recorded at the previous publish.
- If the Confluence page has been edited since the last publish, emit a warning in the build log and proceed with overwrite (do not silently discard the warning).
- Phase 3 may promote this to a build failure pending team decision.

### FR-07: Operational Modes

| Mode | Flag | Behaviour |
|---|---|---|
| Dry run | `--dry-run` | Converts and logs all changes; no API calls |
| Check | `--check` | Validates manifest + syntax; fails if errors found; no publish |
| Validate manifest | `--validate-manifest` | Calls Confluence API to confirm all page IDs exist |
| Sync (default) | _(none)_ | Full convert and publish |

### FR-08: Images (Phase 2)

- Local image files referenced in Markdown (`![alt](path/to/image.png)`) are uploaded as Confluence page attachments.
- The rendered storage format references the attachment by name, not the original path.
- Images must be uploaded before the page content is submitted.
- Remote image URLs are passed through unchanged.

### FR-09: Mermaid Diagrams (Phase 3)

- Fenced code blocks with language label `mermaid` are rendered to PNG using the `mermaid-js` CLI (`mmdc`).
- The PNG is uploaded as an attachment and referenced inline.
- The original Mermaid source is preserved as a hidden comment in the storage format for auditability.

### FR-10: Internal Links (Phase 2)

- Links between managed Markdown files (`[text](../other.md)`) are rewritten to Confluence page links using the manifest.
- Links to files not in the manifest are flagged as warnings (not errors) in Phase 2.

---

## Non-Functional Requirements

### NFR-01: Performance

- Full sync of up to 200 pages must complete within 15 minutes.
- Incremental sync (changed files only) must complete within 5 minutes for up to 20 changed files.

### NFR-02: Rate Limiting

- All Confluence API calls must implement exponential backoff with jitter on 429 responses.
- Maximum retry attempts: 5. After 5 failures, the page is skipped and logged as an error; the build continues for remaining pages but exits non-zero.

### NFR-03: Serialisation

- Page updates must be serialised (not parallelised) to avoid version number conflicts on the same page.
- Different pages may be updated concurrently up to a configurable concurrency limit (default: 3).

### NFR-04: Secrets Management

- `CONFLUENCE_API_TOKEN`: GitHub Actions secret. On DC this is the PAT; on Cloud this is the API token.
- `CONFLUENCE_CERT_PEM`: GitHub Actions secret (DC only). Base64-encoded PEM client certificate. Not required on Cloud.
- `CONFLUENCE_EMAIL`: repository variable (Cloud only). Not used on DC.
- `CONFLUENCE_BASE_URL` and `CONFLUENCE_MODE` (`dc` or `cloud`): repository variables.
- No credentials logged or embedded in output.
- PEM content is decoded and written to a path generated by `tempfile.mkstemp(suffix=".pem")` at startup. The path is dynamic to avoid collisions when multiple jobs share a runner. The file descriptor is closed immediately after writing; the path is passed to the HTTP session and deleted on process exit via `atexit.register(os.unlink, pem_path)`.

### NFR-05: Portability

- The tool must be configurable per-repository via a single config file (`confluence-publisher.yaml`).
- No hardcoded space IDs, parent page IDs, or organisation-specific values.

### NFR-06: Python Version

- Python 3.10+. This is a standalone tool; it is not constrained by the SearchAudit pod environment (Python 3.7).

---

## External Dependencies

| Dependency | Version | Purpose |
|---|---|---|
| `mistletoe` | `>=1.3` | Markdown AST parsing and custom rendering |
| `requests` | `>=2.31` | Confluence REST API calls |
| `PyYAML` | `>=6.0` | Manifest and config file parsing |
| `click` | `>=8.1` | CLI interface |
| `mermaid-js` CLI (`mmdc`) | latest | Mermaid to PNG rendering (Phase 3, Node dependency) |

---

## Confluence API Reference

The client must support both Confluence Data Center (current) and Cloud (target after migration). The two differ in API path and authentication scheme; the Storage Format body representation is the same in both.

### Data Center (current)

| Concern | Detail |
|---|---|
| Base path | `/rest/api/content/` |
| Get page | `GET /rest/api/content/{id}?expand=version,body.storage` |
| Update page | `PUT /rest/api/content/{id}` |
| Create page | `POST /rest/api/content/` |
| Attachments | `POST /rest/api/content/{id}/child/attachment` |
| Authentication | `Authorization: Bearer <PAT>` (Personal Access Token) |
| TLS | Client certificate (PEM) may be required depending on network configuration |
| Space identifier | Space key (string, e.g. `"SEARCHAUDIT"`) |
| Version field | `version.number` (integer, current + 1 on update) |

Authentication follows the same pattern as Jira DC in this codebase: the PAT is read from an environment variable (`CONFLUENCE_API_TOKEN`); an optional PEM client certificate is decoded from a base64 env var (`CONFLUENCE_CERT_PEM`) and written to `/tmp/confluence.pem` at startup.

### Cloud (post-migration target)

| Concern | Detail |
|---|---|
| Base path | `/wiki/api/v2/` |
| Get page | `GET /wiki/api/v2/pages/{id}` |
| Update page | `PUT /wiki/api/v2/pages/{id}` |
| Create page | `POST /wiki/api/v2/pages/` |
| Attachments | `POST /wiki/api/v2/pages/{id}/attachments` |
| Authentication | Basic Auth: `{email}:{api_token}` Base64-encoded |
| TLS | Standard HTTPS; no client certificate |
| Space identifier | Space ID (numeric/UUID) |
| Version field | `version.number` (same semantics as DC) |

### Abstraction

The `ConfluenceClient` accepts a `mode: "dc" | "cloud"` parameter (from config). Auth setup and API path construction branch on this value. All other publisher logic is mode-agnostic. Switching from DC to Cloud requires only a config change.

---

## Out of Scope (Technical)

- OAuth 2.0 / Forge authentication
- Page deletion automation
- Confluence comment preservation
- Macro support beyond what is expressible in Storage Format
