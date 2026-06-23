# Manifest Specification

## Purpose

The manifest (`confluence-manifest.yaml`) is the authoritative mapping between GitHub Markdown file paths and Confluence pages. It is checked into the repository and is the only source of page identity.

Page IDs, not titles, are used as keys. Titles can change; page IDs cannot.

---

## Format

```yaml
version: 1

defaults:
  space_id: "~SPACEID"          # Confluence space identifier
  parent_id: "123456"           # Default parent page for top-level docs

pages:
  docs/architecture.md:
    page_id: "789012"
    title: Architecture Overview
    # space_id and parent_id inherited from defaults

  docs/runbooks/incident-response.md:
    page_id: "789013"
    parent_id: "789012"         # Override: nested under architecture page
    title: Incident Response Runbook

  docs/runbooks/deployment.md:
    page_id: "789014"
    parent_id: "789012"
    title: Deployment Runbook

  # Entry with no page_id triggers auto-creation (Phase 2+)
  docs/new-feature.md:
    title: New Feature Design
    # page_id will be written back here after first publish
```

---

## Fields

### Top-level

| Field | Required | Description |
|---|---|---|
| `version` | Yes | Schema version. Currently `1`. |
| `defaults.space_id` | Yes | Confluence space ID applied to all pages unless overridden. |
| `defaults.parent_id` | No | Default parent page ID. Applied where `parent_id` is not set. |

### Per-page

| Field | Required | Description |
|---|---|---|
| `page_id` | Phase 1: Yes. Phase 2+: No (triggers creation) | Confluence page ID. Survives page renames. |
| `title` | Yes | Confluence page title. Used on create and update. |
| `space_id` | No | Overrides `defaults.space_id` for this page. |
| `parent_id` | No | Overrides `defaults.parent_id`. Determines page hierarchy. |

### Written back by the tool (do not edit manually)

| Field | Written by | Description |
|---|---|---|
| `last_published_hash` | Publisher | SHA-256 of the last published Storage Format content. Used for skip-if-unchanged. |
| `last_published_version` | Publisher | Confluence version number at last publish. Used for edit-conflict detection. |
| `last_published_commit` | Publisher | Git commit SHA at last publish. Informational. |

---

## Rules

1. A file not in the manifest is ignored. The tool does not publish it and does not error.
2. A file that is in the manifest but does not exist on disk is an error (`--check` catches this).
3. A `page_id` that does not exist in Confluence is an error caught by `--validate-manifest`.
4. The `title` field controls the Confluence page title on every publish. Renaming here renames the Confluence page.
5. Do not use the same `page_id` for two different files. The tool will detect and reject duplicate IDs at startup.

---

## Sidecar vs In-Manifest State

The `last_published_*` fields written back by the tool create a question: should the tool commit changes to the manifest file, or write them to a separate sidecar file?

See open question OQ-03 in `DECISIONS.md`.

---

## Example: SearchAudit Pilot

```yaml
version: 1

defaults:
  space_id: "~SEARCHAUDIT"
  parent_id: "100000"           # SearchAudit top-level Confluence page

pages:
  docs/architecture.md:
    page_id: "100001"
    title: SearchAudit Architecture

  docs/etl-pipeline.md:
    page_id: "100002"
    title: ETL Pipeline Overview

  docs/runbooks/redshift-load.md:
    page_id: "100003"
    parent_id: "100002"
    title: Redshift Load Runbook
```
