from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from confluence_publisher.manifest import load_manifest, Manifest
from confluence_publisher.publisher import check_pages, publish_pages, PublishSummary


MANIFEST_DATA = {
    "version": 1,
    "defaults": {"space_id": "TEST"},
    "pages": {
        "docs/arch.md": {"page_id": "111", "title": "Architecture"},
        "docs/runbook.md": {"page_id": "222", "title": "Runbook"},
    },
}


def make_repo(tmp_path: Path, files: dict[str, str] | None = None) -> tuple[Path, Manifest]:
    (tmp_path / "confluence-manifest.yaml").write_text(
        yaml.dump(MANIFEST_DATA, sort_keys=False)
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    default_files = {
        "docs/arch.md": "# Architecture\n\nContent here.\n",
        "docs/runbook.md": "# Runbook\n\nSteps here.\n",
    }
    for path, content in (files or default_files).items():
        (tmp_path / path).write_text(content)
    return tmp_path, load_manifest(tmp_path)


def make_client(version: int = 5) -> MagicMock:
    client = MagicMock()
    client.get_page.return_value = {"version": version, "body": "<p>old</p>"}
    client.update_page.return_value = {"id": "111"}
    return client


# --- Publish flow ---

def test_publish_calls_update_page(tmp_path):
    root, manifest = make_repo(tmp_path)
    client = make_client()
    summary = publish_pages(manifest, ["docs/arch.md"], client, "abc1234", root)
    assert summary.succeeded
    assert len(summary.published) == 1
    client.update_page.assert_called_once()


def test_publish_passes_version_plus_one(tmp_path):
    root, manifest = make_repo(tmp_path)
    client = make_client(version=5)
    publish_pages(manifest, ["docs/arch.md"], client, "abc", root)
    _, kwargs = client.update_page.call_args
    assert kwargs["version"] == 6


def test_publish_passes_commit_sha(tmp_path):
    root, manifest = make_repo(tmp_path)
    client = make_client()
    publish_pages(manifest, ["docs/arch.md"], client, "sha999", root)
    _, kwargs = client.update_page.call_args
    assert kwargs["commit_sha"] == "sha999"


def test_skip_when_hash_unchanged(tmp_path):
    root, manifest = make_repo(tmp_path)
    client = make_client()
    # First publish - sets the hash
    publish_pages(manifest, ["docs/arch.md"], client, "sha1", root)
    client.reset_mock()
    # Second publish with same content - should skip
    summary = publish_pages(manifest, ["docs/arch.md"], client, "sha2", root)
    client.update_page.assert_not_called()
    assert len(summary.skipped) == 1


def test_republish_when_content_changes(tmp_path):
    root, manifest = make_repo(tmp_path)
    client = make_client()
    publish_pages(manifest, ["docs/arch.md"], client, "sha1", root)
    client.reset_mock()
    # Change the file
    (tmp_path / "docs/arch.md").write_text("# New Content\n")
    client.get_page.return_value = {"version": 6, "body": "<p>old</p>"}
    summary = publish_pages(manifest, ["docs/arch.md"], client, "sha2", root)
    client.update_page.assert_called_once()
    assert len(summary.published) == 1


def test_edit_conflict_logs_warning(tmp_path):
    root, manifest = make_repo(tmp_path)
    client = make_client(version=5)
    # First publish at version 5 -> stored version = 6
    publish_pages(manifest, ["docs/arch.md"], client, "sha1", root)
    # Simulate someone manually editing: current version is now 8 (was 6 after our publish)
    client.get_page.return_value = {"version": 8, "body": "<p>manual edit</p>"}
    (tmp_path / "docs/arch.md").write_text("# Updated\n")
    manifest2 = load_manifest(tmp_path)
    summary = publish_pages(manifest2, ["docs/arch.md"], client, "sha2", root)
    conflict = [r for r in summary.results if r.status == "conflict_warned"]
    assert len(conflict) == 1
    assert "8" in conflict[0].message


def test_file_not_in_manifest_is_ignored(tmp_path):
    root, manifest = make_repo(tmp_path)
    client = make_client()
    summary = publish_pages(manifest, ["docs/unknown.md"], client, "sha", root)
    client.update_page.assert_not_called()
    assert len(summary.results) == 0


def test_file_not_on_disk_is_error(tmp_path):
    root, manifest = make_repo(tmp_path)
    client = make_client()
    (tmp_path / "docs/arch.md").unlink()
    summary = publish_pages(manifest, ["docs/arch.md"], client, "sha", root)
    assert not summary.succeeded
    assert "does not exist" in summary.errors[0].message


def test_conversion_error_is_error(tmp_path):
    root, manifest = make_repo(
        tmp_path, files={"docs/arch.md": "![img](photo.png)\n", "docs/runbook.md": "text"}
    )
    client = make_client()
    summary = publish_pages(manifest, ["docs/arch.md"], client, "sha", root)
    assert not summary.succeeded
    client.update_page.assert_not_called()


def test_no_page_id_is_error(tmp_path):
    data = {
        "version": 1,
        "defaults": {},
        "pages": {"docs/arch.md": {"title": "Arch"}},
    }
    (tmp_path / "confluence-manifest.yaml").write_text(yaml.dump(data))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/arch.md").write_text("# Arch\n")
    manifest = load_manifest(tmp_path)
    client = make_client()
    summary = publish_pages(manifest, ["docs/arch.md"], client, "sha", tmp_path)
    assert not summary.succeeded
    assert "page_id" in summary.errors[0].message


def test_api_error_is_error(tmp_path):
    root, manifest = make_repo(tmp_path)
    client = make_client()
    client.get_page.side_effect = Exception("connection refused")
    summary = publish_pages(manifest, ["docs/arch.md"], client, "sha", root)
    assert not summary.succeeded
    assert "connection refused" in summary.errors[0].message


# --- Dry run ---

def test_dry_run_does_not_call_api(tmp_path):
    root, manifest = make_repo(tmp_path)
    client = make_client()
    summary = publish_pages(manifest, ["docs/arch.md"], client, "sha", root, dry_run=True)
    client.update_page.assert_not_called()
    assert len(summary.published) == 1
    assert summary.published[0].message == "dry-run"


def test_dry_run_does_not_save_manifest(tmp_path):
    root, manifest = make_repo(tmp_path)
    client = make_client()
    with patch("confluence_publisher.publisher.save_manifest") as mock_save:
        publish_pages(manifest, ["docs/arch.md"], client, "sha", root, dry_run=True)
        mock_save.assert_not_called()


# --- check_pages ---

def test_check_pages_valid(tmp_path):
    root, manifest = make_repo(tmp_path)
    errors = check_pages(manifest, root)
    assert errors == []


def test_check_pages_missing_file(tmp_path):
    root, manifest = make_repo(tmp_path)
    (tmp_path / "docs/arch.md").unlink()
    errors = check_pages(manifest, root)
    assert any("not found" in e for e in errors)


def test_check_pages_unsupported_syntax(tmp_path):
    root, manifest = make_repo(
        tmp_path, files={"docs/arch.md": "![img](photo.png)", "docs/runbook.md": "text"}
    )
    errors = check_pages(manifest, root)
    assert any("Phase 2" in e for e in errors)
