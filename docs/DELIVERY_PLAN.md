# Delivery Plan

## Approach

Four phases, each producing a working and usable tool. Later phases add syntax support and robustness. No phase leaves the tool in a broken intermediate state.

Pilot repository: SearchAudit (`/Users/deji/Dev/SearchAudit/docs/`)

---

## Phase 1: Core Text Publishing

**Goal**: Publish pre-created Confluence pages from text-heavy Markdown. Engineers can merge docs and see them appear in Confluence within minutes.

**Scope**:
- GitHub Action trigger on `push` to `main` with `paths: ["docs/**/*.md"]`
- `--dry-run`, `--check`, `--validate-manifest` modes
- Manifest-based page mapping (page IDs required; no auto-creation)
- Conversion: headings, paragraphs, bold, italic, inline code, ordered/unordered lists, fenced code blocks (with language label), blockquotes, external hyperlinks
- Generated banner on every published page
- Git commit SHA stored in Confluence version message
- Content hash check (skip if unchanged)
- Edit conflict detection (warn, do not block)
- Exponential backoff on 429 / 5xx responses
- Exit non-zero on any conversion or API error
- `--check` mode runs in PR via a separate workflow step

**Not in scope for Phase 1**:
- Images, internal links, tables, Mermaid, page creation

**Definition of done**:
- SearchAudit docs publishing end-to-end
- `--check` catches unsupported syntax in a test PR
- No silent failures: any conversion error produces a visible build failure

**Estimated effort**: 2-3 weeks

---

## Phase 2: Images, Internal Links, and Page Creation

**Goal**: Handle the most common doc patterns that Phase 1 rejects.

**Scope**:
- Image upload as Confluence attachment before page update
- Internal Markdown links rewritten to Confluence page links using the manifest
- Links to non-manifest files flagged as warnings (not errors)
- Automated page creation for files in the manifest with no existing `page_id`
- After creation, write the assigned `page_id` back to the manifest (via a commit or sidecar - see OQ-03)

**Definition of done**:
- Docs with screenshots and cross-links publish without manual intervention
- Newly added manifest entries without `page_id` auto-create pages and persist the new ID

**Estimated effort**: 2 weeks

---

## Phase 3: Tables, Mermaid, and Edit Conflict Hardening

**Goal**: Support the remaining common Markdown features; tighten safety around overwrites.

**Scope**:
- Table conversion to Confluence storage format `<table>`
- Mermaid fenced blocks rendered to PNG via `mmdc`, uploaded as attachment
- Edit conflict detection promoted from warning to configurable failure (`--strict-conflicts`)
- `--validate-manifest` run on a nightly schedule via `workflow_dispatch` + cron

**Definition of done**:
- Architecture diagrams (Mermaid) appear as images in Confluence
- Tables render correctly
- A manual Confluence edit causes a detectable build warning by default, failure in strict mode

**Estimated effort**: 2 weeks

---

## Phase 4: Reusable Organisation-Level Action

**Goal**: Package the tool so other teams can adopt it with minimal configuration.

**Scope**:
- Published as an internal GitHub Action (composite action or Docker-based)
- Per-repo configuration via `confluence-publisher.yaml` only (no code changes needed to adopt)
- Documentation for onboarding a new repo
- Dry-run preview posted as a PR comment (conversion report with any warnings)
- Optional: publish to PyPI internal registry as `confluence-publisher`

**Definition of done**:
- A second team (outside SearchAudit) adopts the action with only config changes
- Onboarding doc covers: prerequisites, manifest setup, secret configuration, first publish

**Estimated effort**: 1-2 weeks

---

## Timeline Summary

| Phase | Scope | Effort |
|---|---|---|
| 1 | Core text publishing | 2-3 weeks |
| 2 | Images, links, page creation | 2 weeks |
| 3 | Tables, Mermaid, conflict hardening | 2 weeks |
| 4 | Reusable org-level action | 1-2 weeks |
| **Total** | | **7-9 weeks** |

Phases 1 and 2 deliver most of the practical value. Phases 3 and 4 are refinement and scale.

---

## Pilot Acceptance Criteria (Phase 1)

Before rolling out to the wider team, the following must hold for SearchAudit:

- [ ] All `.md` files under `docs/` in SearchAudit are listed in the manifest
- [ ] A push to `main` that changes a doc triggers the Action and updates Confluence within 10 minutes
- [ ] A PR that introduces unsupported Markdown syntax fails the `--check` step
- [ ] Manually editing a published Confluence page triggers a warning on the next publish
- [ ] Running `--dry-run` against the full manifest produces no errors
