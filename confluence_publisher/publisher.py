from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .confluence_client import ConfluenceClient
from .converter import ConversionError, content_hash, convert
from .manifest import Manifest, save_manifest

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    file_path: str
    status: str  # "published" | "skipped" | "conflict_warned" | "error"
    message: str = ""


@dataclass
class PublishSummary:
    results: list[PageResult] = field(default_factory=list)

    @property
    def published(self) -> list[PageResult]:
        return [r for r in self.results if r.status == "published"]

    @property
    def skipped(self) -> list[PageResult]:
        return [r for r in self.results if r.status == "skipped"]

    @property
    def errors(self) -> list[PageResult]:
        return [r for r in self.results if r.status == "error"]

    @property
    def succeeded(self) -> bool:
        return len(self.errors) == 0


def publish_pages(
    manifest: Manifest,
    changed_files: list[str],
    client: ConfluenceClient,
    commit_sha: str,
    repo_root: Path,
    dry_run: bool = False,
) -> PublishSummary:
    summary = PublishSummary()

    for file_path in changed_files:
        entry = manifest.pages.get(file_path)
        if entry is None:
            logger.debug("'%s' not in manifest, skipping", file_path)
            continue

        if not entry.page_id:
            summary.results.append(PageResult(
                file_path=file_path,
                status="error",
                message="No page_id in manifest - auto-creation is not supported until Phase 2.",
            ))
            continue

        full_path = repo_root / file_path
        if not full_path.exists():
            summary.results.append(PageResult(
                file_path=file_path,
                status="error",
                message=f"File does not exist on disk: {full_path}",
            ))
            continue

        try:
            text = full_path.read_text(encoding="utf-8")
            body, full_body = convert(text, file_path, commit_sha)
        except ConversionError as exc:
            summary.results.append(PageResult(
                file_path=file_path,
                status="error",
                message=str(exc),
            ))
            continue

        new_hash = content_hash(body)

        if entry.last_published_hash == new_hash:
            logger.info("'%s' unchanged, skipping", file_path)
            summary.results.append(PageResult(file_path=file_path, status="skipped"))
            continue

        if dry_run:
            logger.info("[dry-run] Would publish '%s'", file_path)
            summary.results.append(PageResult(
                file_path=file_path,
                status="published",
                message="dry-run",
            ))
            continue

        try:
            current = client.get_page(entry.page_id)
        except Exception as exc:
            summary.results.append(PageResult(
                file_path=file_path,
                status="error",
                message=f"Failed to fetch page {entry.page_id}: {exc}",
            ))
            continue

        current_version = current["version"]

        if (
            entry.last_published_version is not None
            and current_version > entry.last_published_version
        ):
            logger.warning(
                "Manual edit detected on '%s' (Confluence version %d, last published %d). "
                "Overwriting with GitHub content.",
                file_path,
                current_version,
                entry.last_published_version,
            )
            summary.results.append(PageResult(
                file_path=file_path,
                status="conflict_warned",
                message=(
                    f"Confluence version {current_version} > "
                    f"last published {entry.last_published_version}"
                ),
            ))

        new_version = current_version + 1
        try:
            client.update_page(
                page_id=entry.page_id,
                title=entry.title,
                body=full_body,
                version=new_version,
                commit_sha=commit_sha,
            )
        except Exception as exc:
            summary.results.append(PageResult(
                file_path=file_path,
                status="error",
                message=f"Failed to update page {entry.page_id}: {exc}",
            ))
            continue

        entry.last_published_hash = new_hash
        entry.last_published_version = new_version
        entry.last_published_commit = commit_sha

        if not any(r.file_path == file_path for r in summary.results):
            summary.results.append(PageResult(file_path=file_path, status="published"))

        logger.info("Published '%s' -> page %s (v%d)", file_path, entry.page_id, new_version)

    if not dry_run:
        save_manifest(manifest)

    return summary


def check_pages(manifest: Manifest, repo_root: Path) -> list[str]:
    """Validate manifest entries and conversion without calling the API.
    Returns a list of error messages; empty list means all clear.
    """
    errors: list[str] = []

    for file_path, entry in manifest.pages.items():
        full_path = repo_root / file_path
        if not full_path.exists():
            errors.append(f"'{file_path}': file not found on disk")
            continue
        try:
            text = full_path.read_text(encoding="utf-8")
            convert(text, file_path, commit_sha="<check>")
        except ConversionError as exc:
            errors.append(str(exc))

    return errors
