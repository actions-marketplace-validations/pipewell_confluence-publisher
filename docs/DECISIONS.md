# Decision Log and Open Questions

Decisions already made are recorded here with their rationale. Open questions are flagged and need resolution before the relevant phase begins.

---

## Decisions Made

### D-01: One-way publishing only

**Decision**: GitHub is the source of truth. Confluence is read-only for managed pages.

**Rationale**: Bidirectional sync requires conflict resolution, which is complex and fragile. The primary value is making GitHub docs accessible to non-engineers, not enabling Confluence-first editing.

---

### D-02: Page IDs over title matching

**Decision**: The manifest uses Confluence `page_id` as the stable identifier, not page titles.

**Rationale**: Title-based lookup breaks when pages are renamed. Page IDs are permanent for the lifetime of the page. This was the key insight that makes the manifest approach work reliably.

---

### D-03: Fail on unsupported syntax, not silent fallback

**Decision**: Any Markdown node the converter does not support raises a `ConversionError` and fails the build.

**Rationale**: Silent degradation produces broken Confluence pages that look superficially correct. Engineers discover the problem when stakeholders read the doc, not in CI. A build failure in PR is much cheaper.

---

### D-04: `mistletoe` as the Markdown parser

**Decision**: Use `mistletoe` for AST-based Markdown parsing and custom rendering.

**Rationale**: `mistletoe` is designed to accept custom renderers, which is exactly what conversion to Confluence Storage Format requires. Alternatives (`markdown2`, `python-markdown`) are string-output-oriented and make AST walking awkward. `commonmark-spec` compliance is a bonus.

---

### D-05: Confluence Storage Format, not ADF

**Decision**: Target Confluence Storage Format (XHTML-based) rather than Atlassian Document Format (ADF).

**Rationale**: The REST API v2 `page` endpoint accepts Storage Format directly via `body.storage`. ADF is the newer format used by the editor, but requires a different representation and the conversion tooling is less mature. Storage Format is stable and well-documented.

---

### D-06: Mermaid rendered to PNG, not macro

**Decision**: Mermaid diagrams are rendered to PNG by `mmdc` in CI and uploaded as attachments.

**Rationale**: Confluence Cloud does not render Mermaid natively. The paid "Mermaid Diagrams" macro exists but introduces a third-party dependency outside our control. Rendering to PNG in CI is deterministic and requires no Confluence configuration.

**Trade-off**: Diagrams are static images; they cannot be edited in Confluence. This is acceptable because the source remains in GitHub.

---

### D-09: Fixed manifest path at repo root

**Decision**: The manifest is always `confluence-manifest.yaml` at the repository root. No configurable path.

**Rationale**: Opinionated convention removes a configuration decision for every adopting team. Anyone looking at a repo can immediately find the manifest without reading docs.

---

### D-10: Info macro banner on all published pages

**Decision**: Every published page opens with an `ac:structured-macro ac:name="info"` block containing the source file path and Git commit SHA.

**Rationale**: The blue Info panel is visually distinct and available in both Confluence DC and Cloud. Plain text is too easy to miss; the Note (yellow) macro would feel alarmist for routine doc pages. The Info macro makes it unambiguous that the page is managed and that manual edits will be overwritten.

**Storage Format**:
```xml
<ac:structured-macro ac:name="info">
  <ac:rich-text-body>
    <p>This page is auto-generated from GitHub. Manual edits will be overwritten on next publish.<br/>
    Source: <code>docs/architecture.md</code> @ <code>a1b2c3d</code></p>
  </ac:rich-text-body>
</ac:structured-macro>
```

---

### D-11: Manifest state writeback via commit to main

**Decision**: After a successful publish run, the tool commits the updated `confluence-manifest.yaml` (with `last_published_hash`, `last_published_version`, `last_published_commit` written back) directly to the default branch from within the GitHub Action.

**Rationale**: Single file, single source of truth. Simpler to audit than a sidecar. Avoids fetching live Confluence content on every run just to check for changes.

**Requirements**:
- Action token needs `contents: write` permission (set in the workflow `permissions` block).
- The automated commit message must include `[skip ci]` to prevent the Action from re-triggering on its own writeback commit.
- Commit author should be a named bot identity (e.g. `confluence-publisher-bot <noreply@...>`) so it is distinguishable in git log.

---

### D-08: Rate limiting via semaphore + tenacity (resolved from Jira DC implementation)

**Decision**: Use an `asyncio.Semaphore` for concurrency control and `tenacity` with exponential backoff for 429/5xx retry. No `--delay-between-pages` flag needed.

**Rationale**: The Jira DC integration (`ingest/jira/src/jira_api.py`) uses this combination and handled Jira's rate limits reliably in production. The semaphore bounds concurrent in-flight requests; tenacity handles transient failures without a fixed sleep that would slow every page regardless of load.

**Parameters** (adapted from Jira DC, adjusted for synchronous page updates):
- `MAX_REQUESTS` (semaphore size): configurable via `confluence-publisher.yaml`, default `3` (lower than Jira's `10` because page updates are heavier operations than reads)
- Tenacity: `wait_exponential(multiplier=1, min=4, max=300)`, `stop_after_attempt(5)` (Jira used 20; 5 is sufficient for publishing - after 5 failures the page is skipped and the build exits non-zero)
- Retry on: `RequestException`, `ConnectionError`, `ReadTimeout`, `SSLError`, HTTP 429 and 5xx

**Config surface**: `MAX_REQUESTS` in `confluence-publisher.yaml`. No per-page delay flag.

---

### D-07: Dual-mode client supporting DC and Cloud

**Decision**: The `ConfluenceClient` accepts a `mode` parameter (`"dc"` or `"cloud"`). Auth setup and API path construction branch on this value; all publisher logic above the client is mode-agnostic. Switching from DC to Cloud requires only a config/secret change, no code change.

**Rationale**: The team is currently on Confluence Data Center and migrating to Cloud. Building a single abstraction now avoids a code rewrite at migration time. The two modes differ only in API base path, authentication header, and whether a client certificate is needed.

**DC auth pattern**: based on the proven Jira DC integration at `ingest/jira/src/` (legacy, but confirmed working):
- `Authorization: Bearer <PAT>` header
- Optional PEM client certificate decoded from `CONFLUENCE_CERT_PEM` (base64 env var) and written via `tempfile.mkstemp(suffix=".pem")` at startup - dynamic path to avoid collisions on shared runners (improvement on the Jira DC code which used a fixed `/tmp/certificate.pem`). Cleaned up on exit via `atexit.register(os.unlink, pem_path)`.

**Cloud auth pattern**: Basic Auth with `{email}:{api_token}` Base64-encoded. No client certificate.

**Config surface**: `CONFLUENCE_MODE=dc|cloud`, `CONFLUENCE_BASE_URL`, `CONFLUENCE_API_TOKEN`, `CONFLUENCE_CERT_PEM` (DC only), `CONFLUENCE_EMAIL` (Cloud only) - all via GitHub Actions secrets/variables.

---

## Open Questions


### OQ-04: Handling pages removed from the manifest

**Question**: If a file is removed from the manifest (or deleted from GitHub), what happens to the Confluence page?

**Options**:
- A: Do nothing. Manual cleanup required. (Phase 1 default)
- B: Archive the Confluence page (move to an archive space or parent)
- C: Delete the Confluence page

**Recommendation**: Option A for all phases unless explicitly requested. Deletion is irreversible and risks removing content that stakeholders depend on. Flag removed entries as warnings in `--validate-manifest`.

**Blocking**: No. Can remain as Option A indefinitely.

---

### OQ-05: PR preview comment

**Question**: Should the `--check` run in PRs post a comment summarising what will be published (pages changed, any warnings)?

**Options**:
- A: No comment. Build pass/fail is sufficient.
- B: Post a summary comment via `gh` CLI (pages to be updated, warnings, skipped pages)
- C: Post a full diff of Confluence Storage Format (too verbose)

**Recommendation**: Option B in Phase 4. Low priority for Phase 1.

**Blocking**: No.

---

