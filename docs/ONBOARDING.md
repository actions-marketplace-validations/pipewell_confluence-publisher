# Onboarding a new repository

This guide walks through connecting a GitHub repository to Confluence so that
Markdown files in `docs/` are published automatically whenever they change on
`main`.

The tool is a **one-way sync**: GitHub is the source of truth. Changes made
directly in Confluence will be overwritten on the next publish.

---

## Prerequisites

- A Confluence Cloud account with at least Space Admin access to the target space
- A GitHub repository containing Markdown documentation
- Permission to add repository secrets and variables

---

## Step 1: Create a Confluence API token

1. Go to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token** and give it a memorable label (e.g. `github-publisher`)
3. Copy the token value — you will not be able to see it again

For Confluence Data Centre, generate a Personal Access Token from your profile
page instead.

---

## Step 2: Configure GitHub secrets and variables

In your repository go to **Settings > Secrets and variables > Actions**.

Add these **secrets** (values are encrypted and hidden from logs):

| Secret | Value |
|---|---|
| `CONFLUENCE_API_TOKEN` | The API token you just created |

Add these **variables** (values are visible to workflow authors):

| Variable | Example value | Notes |
|---|---|---|
| `CONFLUENCE_BASE_URL` | `https://your-org.atlassian.net` | No trailing slash |
| `CONFLUENCE_MODE` | `cloud` | Use `dc` for Data Centre |
| `CONFLUENCE_EMAIL` | `your.name@example.com` | Cloud only; omit for DC |

---

## Step 3: Create the manifest

Add a `confluence-manifest.yaml` file at the root of your repository.

### Minimal example

```yaml
defaults:
  space_id: ENG            # Confluence space key
  parent_id: '123456'      # Page ID of the parent page in that space

pages:
  docs/architecture.md:
    title: Architecture Overview
    page_id: '234567'      # Existing Confluence page ID

  docs/runbook.md:
    title: Operations Runbook
    # No page_id — the page will be created automatically on first publish
```

### Finding a page ID

Open the page in Confluence, click the three-dot menu (top-right), then
**Page information**. The page ID is in the URL:
`…/pages/viewinfo.action?pageId=234567`

### Per-page space or parent overrides

```yaml
pages:
  docs/team/roadmap.md:
    title: Team Roadmap
    space_id: TEAM          # overrides the default space
    parent_id: '987654'     # overrides the default parent
```

---

## Step 4: Add the workflow files

Copy the example workflows from this repository into your `.github/workflows/`
directory:

```
examples/workflows/publish.yml   ->  .github/workflows/publish-to-confluence.yml
examples/workflows/pr-preview.yml -> .github/workflows/confluence-pr-preview.yml
```

Both files reference `donolu/confluence-publisher@v1`, which is the reusable
action. No further code is needed in your repository.

---

## Step 5: First publish

Either push a change to a file listed in your manifest, or trigger the workflow
manually:

1. Go to **Actions** in your repository
2. Select **Publish docs to Confluence**
3. Click **Run workflow** and tick **Sync all manifest entries**

The first run will create any pages where `page_id` is absent, then write those
IDs back to `confluence-manifest.yaml` via a `[skip ci]` commit.

---

## Local testing

Install the tool in a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
pip install git+https://github.com/donolu/confluence-publisher.git@v1
```

Copy `.env.example` to `.env` and fill in your credentials, then:

```bash
# Validate syntax without calling Confluence
confluence-publisher check

# See what would be published (no API calls)
confluence-publisher sync --dry-run

# Publish for real
confluence-publisher sync
```

---

## Supported Markdown features

| Feature | Support |
|---|---|
| Headings (H1-H6) | Full |
| Bold, italic, inline code | Full |
| Fenced code blocks (with language) | Full |
| Tables | Full |
| Ordered and unordered lists | Full |
| Nested lists | Full |
| Blockquotes | Full |
| Horizontal rules | Full |
| External links | Full |
| Internal links (relative `.md` paths) | Resolved to Confluence page links |
| Local images | Uploaded as page attachments |
| External images | Rendered inline |
| Mermaid diagrams | Rendered to PNG (requires `mmdc` in CI) |
| Hard and soft line breaks | Full |
| Strikethrough | Not supported — raises a conversion error |
| Raw HTML | Not supported — raises a conversion error |

---

## Conflict handling

If a Confluence page is manually edited after the last publish, the tool will
log a warning and overwrite with the GitHub content (GitHub is always the
source of truth).

To make conflicts fail the build instead of just warning, pass
`--strict-conflicts` to the `sync` command (or set `strict-conflicts: 'true'`
on the action). The page is still updated; the non-zero exit code surfaces the
conflict to the PR author.

---

## Troubleshooting

### `page_id not found` on validate-manifest

The Confluence page was deleted or moved. Either restore it in Confluence or
remove the `page_id` entry from the manifest so it is recreated automatically.

### Conversion error: Strikethrough not supported

Remove `~~strikethrough~~` syntax from the file, or rewrite it as plain text.

### Image not found on disk

The path in the Markdown image tag does not exist relative to the repository
root. Verify the path is correct and the file is committed.

### `mmdc` not found in CI

The Mermaid CLI is only installed in the `publish` job. If you see this warning
on `check` runs, it is expected — diagrams are only rendered during publish.

### Credentials error (401 or 403)

- Confirm `CONFLUENCE_BASE_URL` has no trailing slash
- Verify the API token has not expired
- For Cloud, ensure `CONFLUENCE_EMAIL` matches the account that owns the token
- For DC, confirm the Personal Access Token has write access to the target space
