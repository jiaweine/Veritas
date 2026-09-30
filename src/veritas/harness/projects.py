from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import utc_now_iso

PROJECT_SCHEMA_VERSION = "1"
MAX_PROJECT_NAME_CHARS = 80
MAX_PROJECTS = 500


class ProjectStore:
    """Local, non-evidentiary grouping metadata for audit workspaces.

    Projects deliberately live outside each paper/evidence record. They organize
    audits for the product UI but do not change detector inputs, findings,
    provenance, notes, or execution artifacts.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "projects.json"
        self._lock = threading.RLock()

    def list_projects(self) -> list[dict[str, Any]]:
        with self._lock:
            value = self._read()
            projects = [dict(item) for item in value["projects"]]
        projects.sort(key=lambda item: str(item["created_at"]))
        return projects

    def create_project(self, name: str) -> dict[str, Any]:
        clean_name = self._clean_name(name)
        with self._lock:
            value = self._read()
            if len(value["projects"]) >= MAX_PROJECTS:
                raise ValueError(f"project limit reached ({MAX_PROJECTS})")
            if any(
                str(item["name"]).casefold() == clean_name.casefold()
                for item in value["projects"]
            ):
                raise ValueError(f"project already exists: {clean_name}")
            now = utc_now_iso()
            project = {
                "project_id": f"project_{uuid4().hex[:12]}",
                "name": clean_name,
                "created_at": now,
                "updated_at": now,
            }
            value["projects"].append(project)
            self._write(value)
            return dict(project)

    def get_project(self, project_id: str) -> dict[str, Any]:
        self._validate_project_id(project_id)
        with self._lock:
            value = self._read()
            project = next(
                (item for item in value["projects"] if item["project_id"] == project_id),
                None,
            )
            if project is None:
                raise FileNotFoundError(f"project not found: {project_id}")
            return dict(project)

    def assign_audit(self, audit_id: str, project_id: str | None) -> str | None:
        self._validate_audit_id(audit_id)
        normalized = project_id.strip() if isinstance(project_id, str) else None
        if normalized == "":
            normalized = None
        with self._lock:
            value = self._read()
            if normalized is not None:
                self._validate_project_id(normalized)
                if not any(item["project_id"] == normalized for item in value["projects"]):
                    raise FileNotFoundError(f"project not found: {normalized}")
                value["assignments"][audit_id] = normalized
            else:
                value["assignments"].pop(audit_id, None)
            self._write(value)
        return normalized

    def project_for_audit(self, audit_id: str) -> str | None:
        self._validate_audit_id(audit_id)
        with self._lock:
            value = self._read()
            assigned = value["assignments"].get(audit_id)
            return str(assigned) if assigned is not None else None

    def assignments(self) -> dict[str, str]:
        with self._lock:
            value = self._read()
            return dict(value["assignments"])

    def snapshot(self, audit_ids: list[str]) -> dict[str, Any]:
        """Return the UI grouping projection for an explicit audit universe.

        The audit universe comes from the authoritative Harness store. Stale
        assignments for manually removed audit directories are not surfaced as
        current product state and are never folded into audit/evidence JSON.
        """

        normalized_ids: list[str] = []
        seen: set[str] = set()
        for audit_id in audit_ids:
            self._validate_audit_id(audit_id)
            if audit_id not in seen:
                seen.add(audit_id)
                normalized_ids.append(audit_id)

        with self._lock:
            value = self._read()
            assignments = {
                audit_id: project_id
                for audit_id, project_id in value["assignments"].items()
                if audit_id in seen
            }
            grouped: dict[str, list[str]] = {
                str(project["project_id"]): [] for project in value["projects"]
            }
            for audit_id in normalized_ids:
                project_id = assignments.get(audit_id)
                if project_id in grouped:
                    grouped[project_id].append(audit_id)
            projects = [
                {
                    **dict(project),
                    "audit_ids": grouped[str(project["project_id"])],
                    "audit_count": len(grouped[str(project["project_id"])]),
                }
                for project in value["projects"]
            ]

        projects.sort(key=lambda item: str(item["created_at"]))
        unassigned = [audit_id for audit_id in normalized_ids if audit_id not in assignments]
        return {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "projects": projects,
            "assignments": assignments,
            "unassigned_audit_ids": unassigned,
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schema_version": PROJECT_SCHEMA_VERSION,
                "projects": [],
                "assignments": {},
            }
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError("project metadata must be an object")
        if value.get("schema_version") != PROJECT_SCHEMA_VERSION:
            raise ValueError("unsupported project metadata schema")
        projects = value.get("projects")
        assignments = value.get("assignments")
        if not isinstance(projects, list) or any(not isinstance(item, dict) for item in projects):
            raise TypeError("project metadata projects must be an array of objects")
        if not isinstance(assignments, dict):
            raise TypeError("project metadata assignments must be an object")

        known_ids: set[str] = set()
        known_names: set[str] = set()
        for project in projects:
            project_id = project.get("project_id")
            name = project.get("name")
            created_at = project.get("created_at")
            updated_at = project.get("updated_at")
            if not isinstance(project_id, str):
                raise TypeError("project id must be text")
            self._validate_project_id(project_id)
            if project_id in known_ids:
                raise ValueError(f"duplicate project id: {project_id}")
            known_ids.add(project_id)
            clean_name = self._clean_name(name)
            if clean_name != name:
                raise ValueError(f"project name is not canonical: {name!r}")
            folded = clean_name.casefold()
            if folded in known_names:
                raise ValueError(f"duplicate project name: {clean_name}")
            known_names.add(folded)
            if not isinstance(created_at, str) or not isinstance(updated_at, str):
                raise TypeError("project timestamps must be text")

        for audit_id, project_id in assignments.items():
            self._validate_audit_id(audit_id)
            if not isinstance(project_id, str):
                raise TypeError("project assignment id must be text")
            self._validate_project_id(project_id)
            if project_id not in known_ids:
                raise ValueError(f"project assignment references missing project: {project_id}")
        return value

    def _write(self, value: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    @staticmethod
    def _clean_name(name: object) -> str:
        if not isinstance(name, str):
            raise TypeError("project name must be text")
        clean = " ".join(name.split())
        if not clean:
            raise ValueError("project name must not be empty")
        if len(clean) > MAX_PROJECT_NAME_CHARS:
            raise ValueError(
                f"project name exceeds the {MAX_PROJECT_NAME_CHARS} character limit"
            )
        return clean

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not isinstance(project_id, str):
            raise TypeError("project id must be text")
        if not project_id.startswith("project_") or not project_id[8:].isalnum():
            raise ValueError("invalid project id")

    @staticmethod
    def _validate_audit_id(audit_id: str) -> None:
        if not isinstance(audit_id, str):
            raise TypeError("audit id must be text")
        if not audit_id.startswith("audit_") or not audit_id[6:].isalnum():
            raise ValueError(f"invalid project assignment audit id: {audit_id!r}")
