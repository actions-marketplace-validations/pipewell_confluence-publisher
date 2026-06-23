# confluence-publisher

A one-way publishing pipeline that syncs GitHub Markdown files to Confluence pages.

GitHub is the source of truth. Confluence is the generated presentation layer.

## Status

Planning phase. See `docs/` for all pre-project documents.

## Documents

| Document | Purpose |
|---|---|
| [docs/BRD.md](docs/BRD.md) | Business requirements, goals, and success metrics |
| [docs/TRD.md](docs/TRD.md) | Technical requirements, constraints, and API notes |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, component breakdown, conversion pipeline |
| [docs/DELIVERY_PLAN.md](docs/DELIVERY_PLAN.md) | Phased roadmap with scope per phase |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decision log and open questions |
| [docs/MANIFEST_SPEC.md](docs/MANIFEST_SPEC.md) | Page mapping manifest specification |

## Quick Summary

- Triggered by GitHub Actions on merge to `main` when files under `docs/**/*.md` change
- A Python CLI converts changed Markdown files into Confluence Storage Format
- Page identity is managed via a checked-in YAML manifest (page IDs, not titles)
- Updates are versioned; the Git commit SHA is stored in the Confluence version message
- Unsupported Markdown syntax fails the build rather than silently producing broken pages

## Scope Boundary

This tool is not:
- A bidirectional sync
- A real-time mirror
- A general Markdown renderer for arbitrary Confluence content
