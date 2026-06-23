# Architecture

## System Diagram

```
GitHub Repository
│
├── docs/**/*.md          (source files)
├── confluence-manifest.yaml
└── .github/workflows/
    └── publish-to-confluence.yml
             │
             │  on push to main (paths filter)
             ▼
    GitHub Actions Runner
             │
             │  python -m confluence_publisher sync --changed-files ...
             ▼
    ┌─────────────────────────────────────────────────┐
    │              confluence-publisher CLI            │
    │                                                 │
    │  1. Load manifest + config                       │
    │  2. Resolve changed files against manifest       │
    │  3. For each file:                               │
    │     a. Parse Markdown → AST (mistletoe)         │
    │     b. Walk AST → Confluence Storage Format      │
    │     c. Hash rendered content                    │
    │     d. Compare against current Confluence page   │
    │     e. Skip if unchanged                        │
    │     f. Check for manual edit conflict            │
    │     g. Upload attachments (Phase 2)             │
    │     h. PUT page with version + 1                │
    │  4. Exit 0 (success) or 1 (any error)           │
    └─────────────────────────────────────────────────┘
             │
             │  Confluence REST API v2
             ▼
    Confluence Cloud
    └── Target Space
        └── Pages (identified by page_id)
```

---

## Component Breakdown

### 1. CLI Entry Point (`confluence_publisher/cli.py`)

- `sync` command: main publish flow
- `check` command: validate manifest + syntax, no API calls
- `validate-manifest` command: confirm all page IDs exist in Confluence
- `dry-run` flag: convert and log, no publish

### 2. Manifest Loader (`confluence_publisher/manifest.py`)

Reads `confluence-manifest.yaml`. Returns a dict of `{file_path: PageEntry}`.

```python
@dataclass
class PageEntry:
    page_id: str
    space_id: str
    parent_id: str
    title: str
    last_published_hash: str | None   # written back after each successful publish
    last_published_version: int | None
```

The manifest is the only persistent state. After a successful publish, the tool writes back `last_published_hash` and `last_published_version` and commits the update (or writes to a sidecar file - see open question OQ-03).

### 3. Converter (`confluence_publisher/converter.py`)

Uses `mistletoe` with a custom `ConfluenceRenderer` that walks the AST and emits Confluence Storage Format XML.

```
MarkdownDocument
  └── Heading → <h1>, <h2> ...
  └── Paragraph → <p>
  └── CodeFence → <ac:structured-macro ac:name="code">
                    <ac:parameter ac:name="language">python</ac:parameter>
                    <ac:plain-text-body><![CDATA[...]]></ac:plain-text-body>
                  </ac:structured-macro>
  └── Table → <table><tbody><tr><td> ...
  └── Image → (Phase 2) replaced with attachment reference
  └── Link → <a href="..."> or (Phase 2) <ac:link> for internal
  └── UnknownNode → raise ConversionError
```

The renderer is the primary engineering surface of the project. Each supported node type is a discrete, testable method.

### 4. Confluence Client (`confluence_publisher/confluence_client.py`)

Thin wrapper around `requests`. All API calls go through here. Supports both Confluence Data Center (current) and Cloud (post-migration), selected by `CONFLUENCE_MODE` config.

```python
class ConfluenceClient:
    def __init__(self, base_url: str, token: str, mode: str, email: str = None, pem_path: str = None):
        self.mode = mode  # "dc" or "cloud"
        self._session = self._build_session(token, email, pem_path)

    def _build_session(self, token, email, pem_path) -> requests.Session:
        session = requests.Session()
        if self.mode == "dc":
            session.headers["Authorization"] = f"Bearer {token}"
            if pem_path:
                session.cert = pem_path      # dynamic path from tempfile.mkstemp(), not /tmp/fixed.pem
        else:  # cloud
            encoded = base64.b64encode(f"{email}:{token}".encode()).decode()
            session.headers["Authorization"] = f"Basic {encoded}"
        return session

    def _api_path(self, resource: str) -> str:
        if self.mode == "dc":
            return f"/rest/api/content/{resource}"
        return f"/wiki/api/v2/{resource}"
```

Public methods (mode-agnostic callers):
- `get_page(page_id)` - fetch current version + content body
- `update_page(page_id, title, body, version)` - versioned PUT
- `create_page(space_key_or_id, parent_id, title, body)` - POST (Phase 2)
- `upload_attachment(page_id, file_path)` - POST attachment (Phase 2)
- `_request(method, path, **kwargs)` - shared retry + backoff logic (exponential, max 5 attempts)

### 5. Publisher (`confluence_publisher/publisher.py`)

Orchestrates the per-page flow: load page, check hash, check edit conflict, upload attachments, update page, write back manifest state.

### 6. GitHub Action (`.github/workflows/publish-to-confluence.yml`)

```yaml
on:
  push:
    branches: [main]
    paths: ["docs/**/*.md"]
  workflow_dispatch:

permissions:
  contents: write         # required for manifest state writeback commit

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2          # needed to diff changed files

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - run: pip install -e .

      - name: Publish changed docs
        env:
          CONFLUENCE_API_TOKEN: ${{ secrets.CONFLUENCE_API_TOKEN }}
          CONFLUENCE_CERT_PEM: ${{ secrets.CONFLUENCE_CERT_PEM }}   # DC only
          CONFLUENCE_EMAIL: ${{ vars.CONFLUENCE_EMAIL }}             # Cloud only
          CONFLUENCE_BASE_URL: ${{ vars.CONFLUENCE_BASE_URL }}
          CONFLUENCE_MODE: ${{ vars.CONFLUENCE_MODE }}               # "dc" or "cloud"
        run: |
          CHANGED=$(git diff --name-only HEAD~1 HEAD -- 'docs/**/*.md')
          python -m confluence_publisher sync --changed-files $CHANGED

      - name: Commit manifest state
        run: |
          git config user.name "confluence-publisher-bot"
          git config user.email "noreply@github.com"
          git add confluence-manifest.yaml
          git diff --cached --quiet || git commit -m "chore: update confluence-manifest state [skip ci]"
          git push
```

---

## Conversion: Supported Node Map

| Markdown | Confluence Storage Format |
|---|---|
| `# Heading` | `<h1>` |
| `**bold**` | `<strong>` |
| `_italic_` | `<em>` |
| `` `inline code` `` | `<code>` |
| `- list item` | `<ul><li>` |
| `1. list item` | `<ol><li>` |
| ` ```python ` | `<ac:structured-macro ac:name="code">` |
| `> blockquote` | `<blockquote>` |
| `[text](url)` | `<a href="url">` |
| `![alt](img)` | attachment reference (Phase 2) |
| `[text](other.md)` | `<ac:link>` (Phase 2) |
| Mermaid block | PNG attachment (Phase 3) |
| `\| table \|` | `<table>` (Phase 3) |

---

## File Layout

```
confluence-publisher/
├── confluence_publisher/
│   ├── __init__.py
│   ├── cli.py
│   ├── manifest.py
│   ├── converter.py
│   ├── confluence_client.py
│   └── publisher.py
├── tests/
│   ├── test_converter.py
│   ├── test_manifest.py
│   ├── test_publisher.py
│   └── fixtures/
│       └── sample.md
├── docs/                         (project planning)
├── confluence-manifest.yaml      (checked in, updated by tool)
├── confluence-publisher.yaml     (repo-level config)
├── pyproject.toml
└── .github/
    └── workflows/
        └── publish-to-confluence.yml
```

---

## Security Considerations

- API token lives in GitHub Actions secrets only; never logged.
- The generated banner on every Confluence page makes provenance explicit.
- The tool never reads Confluence content back into the build artefact (read is only for version number and hash comparison).
- No user-supplied content is interpolated into shell commands (all API calls use `requests`, not `subprocess`).
