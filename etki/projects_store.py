"""Writable store for projects.yaml + project workspace management (project
setup from the UI).

Projects are written to config/projects.yaml (config-driven). Each project's
workspace lives under `.etki/projects/{id}/`: `docs/` (uploaded spec →
text), `repos/{name}/` (clones). After a write, the caller (api) clears the
context cache.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import yaml

from etki.adapters.git_clone import clone
from etki.config import ConnectorConfig, ProjectConfig, RepoConfig, Settings, load_projects
from etki.extraction.parsers import parse_document

_WORKSPACE = Path(".etki/projects")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_id(value: str, kind: str = "tanımlayıcı") -> str:
    """Path-traversal guard: only letters/digits/_/- are accepted."""
    value = value.strip()
    if not _SAFE_ID.match(value):
        raise ValueError(f"geçersiz {kind}: yalnızca harf, rakam, '_' ve '-' kullanılabilir")
    return value


def _workspace(project_id: str) -> Path:
    return _WORKSPACE / _validate_id(project_id, "proje id")


def load() -> list[ProjectConfig]:
    settings = Settings()
    return load_projects(settings.projects_path, settings.connectors_path)


def get(project_id: str) -> ProjectConfig | None:
    return next((p for p in load() if p.id == project_id), None)


def _require(project_id: str) -> ProjectConfig:
    project = get(project_id)
    if project is None:
        raise KeyError(f"proje bulunamadı: {project_id}")
    return project


def save(projects: list[ProjectConfig], path: str | None = None) -> None:
    target = Path(path or Settings().projects_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"projects": [p.model_dump(exclude_none=True) for p in projects]}
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    # Atomic write: temp + os.replace → a partial write can't corrupt projects.yaml.
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, target)


def _upsert(updated: ProjectConfig) -> None:
    projects = load()
    if any(p.id == updated.id for p in projects):
        projects = [updated if p.id == updated.id else p for p in projects]
    else:
        projects.append(updated)
    save(projects)


def create_project(project_id: str, name: str, contract_id: str) -> ProjectConfig:
    project_id = _validate_id(project_id, "proje id")
    if get(project_id) is not None:
        raise ValueError(f"proje zaten var: {project_id}")
    docs = _workspace(project_id) / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    project = ProjectConfig(
        id=project_id, name=name, contract_id=contract_id, doc_root=str(docs)
    )
    # A new project has no historical work items → 'none' (so fake seed tickets don't
    # leak into effort; effort comes from code metrics). The user can later attach
    # Jira/GLPI/file from the UI.
    project.connectors.work_items = ConnectorConfig(adapter="none")
    _upsert(project)
    return project


def add_documents(project_id: str, files: list[tuple[str, bytes]]) -> int:
    """Converts uploaded spec/requirement files to text and writes them to the
    project's docs directory."""
    project = _require(project_id)
    docs = Path(project.doc_root) if project.doc_root else _workspace(project_id) / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    written = 0
    for filename, data in files:
        text, _ = parse_document(filename, data)
        if text.strip():
            (docs / f"{Path(filename).stem}.md").write_text(text, encoding="utf-8")
            written += 1
    if not project.doc_root:
        project.doc_root = str(docs)
        _upsert(project)
    return written


def add_repo(
    project_id: str,
    name: str,
    *,
    git_url: str | None = None,
    src_root: str | None = None,
    engine: str = "ast",
) -> RepoConfig:
    """Adds a code repo to the project (git URL → clone, or a local path)."""
    project = _require(project_id)
    name = _validate_id(name, "repo adı")  # path-traversal guard (workspace subdirectory)
    if git_url:
        src_root = clone(git_url, _workspace(project_id) / "repos" / name)
    if not src_root:
        raise ValueError("git_url veya src_root gerekli")
    repo = RepoConfig(name=name, src_root=src_root, git_url=git_url, engine=engine)
    project.repos = [r for r in project.repos if r.name != name] + [repo]
    _upsert(project)
    return repo


def set_work_items(project_id: str, adapter: str, options: dict) -> ProjectConfig:
    """Sets the project's work-tracking / PM environment (file | jira | glpi)."""
    project = _require(project_id)
    project.connectors.work_items = ConnectorConfig(adapter=adapter, options=options)
    _upsert(project)
    return project


def set_llm_profile(
    project_id: str,
    *,
    language: str,
    domain_profile: str | None,
    instructions: str,
    pivot_language: str | None,
) -> ProjectConfig:
    """Sets the project's LLM profile: output language + domain profile + free-text
    instructions + pivot.

    Does not affect the index (LLM path only); the caller just clears the context cache."""
    project = _require(project_id)
    project.language = language.strip() or "tr"
    project.domain_profile = (domain_profile or "").strip() or None
    project.instructions = instructions.strip()
    project.pivot_language = (pivot_language or "").strip() or None
    _upsert(project)
    return project


def _docs_dir(project: ProjectConfig) -> Path:
    return Path(project.doc_root) if project.doc_root else _workspace(project.id) / "docs"


def list_documents(project_id: str) -> list[dict]:
    """Spec/requirement files uploaded to the project (in the workspace docs directory)."""
    project = get(project_id)
    if project is None:
        return []
    root = _docs_dir(project)
    if not root.exists():
        return []
    files = (f for f in root.iterdir() if f.is_file() and f.suffix in (".md", ".txt"))
    return [{"name": f.name, "size": f.stat().st_size} for f in sorted(files)]


def delete_document(project_id: str, filename: str) -> bool:
    """Deletes an uploaded spec file (path-traversal protected)."""
    project = _require(project_id)
    target = _docs_dir(project) / Path(filename).name  # only a file within the docs root
    if target.is_file():
        target.unlink()
        return True
    return False


def delete_repo(project_id: str, name: str) -> bool:
    """Removes a code repo from the project; also cleans up the cloned workspace
    directory."""
    project = _require(project_id)
    removed = [r for r in project.repos if r.name == name]
    if not removed:
        return False
    project.repos = [r for r in project.repos if r.name != name]
    _upsert(project)
    workspace_repo = _workspace(project_id) / "repos" / name
    if removed[0].git_url and workspace_repo.exists():  # only delete clones
        shutil.rmtree(workspace_repo, ignore_errors=True)
    return True


def delete_project(project_id: str) -> bool:
    """Deletes the project definition from projects.yaml, plus the workspace +
    index file.

    Historical decision files (audit trail) in the database are preserved — not
    deleted. The decision wiki (`.etki/wiki-{id}/`) is preserved for the same
    reason: it is a readable projection of that same audit history (regenerable
    via `python -m etki.wiki rebuild`)."""
    projects = load()
    target = next((p for p in projects if p.id == project_id), None)
    if target is None:
        return False
    save([p for p in projects if p.id != project_id])
    workspace = _workspace(project_id)
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
    index_file = Path(target.resolved_index_path())
    if index_file.exists():
        index_file.unlink()
    return True
