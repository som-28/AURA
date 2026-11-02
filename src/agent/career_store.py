"""Small atomic store for a local user's career profile and job pipeline."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from src.agent.state_store import get_database_backend


PROFILE_FIELDS = {
    "name", "current_role", "years_experience", "experience_evidence", "skills",
    "education", "field_of_study", "career_interests", "industries", "achievements",
    "job_keywords", "summary", "email", "phone", "links",
}
PREFERENCE_FIELDS = {"target_role", "location", "work_mode", "keywords", "min_salary", "digest_email", "digest_frequency"}
ROLE_STATUSES = {"saved", "applied", "interview", "rejected", "offer", "archived"}


class CareerStore:
    def __init__(self, path: str | None = None):
        self.path = Path(path or os.getenv("AURA_CAREER_STORE", ".aura_career.json"))
        self.resume_directory = self.path.parent / f"{self.path.stem}_files"
        self.database = get_database_backend() if path is None else None

    def _read(self) -> dict:
        if self.database:
            value = self.database.read_state("career", {})
            if not isinstance(value, dict):
                value = {}
            value.setdefault("profile", None)
            value.setdefault("identity", {})
            value.setdefault("resume", None)
            value.setdefault("preferences", {})
            value.setdefault("roles", [])
            value.setdefault("digest_urls", [])
            value.setdefault("last_digest", None)
            return value
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                value.setdefault("profile", None)
                value.setdefault("identity", {})
                value.setdefault("resume", None)
                value.setdefault("preferences", {})
                value.setdefault("roles", [])
                value.setdefault("digest_urls", [])
                value.setdefault("last_digest", None)
                return value
        except (OSError, json.JSONDecodeError):
            pass
        return {"profile": None, "identity": {}, "resume": None, "preferences": {}, "roles": [], "digest_urls": [], "last_digest": None}

    def _write(self, data: dict) -> None:
        if self.database:
            self.database.write_state("career", data)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def profile(self) -> dict | None:
        data = self._read()
        profile = data.get("profile") or {}
        identity = data.get("identity") or {}
        merged = {**profile, **identity}
        return merged or None

    def save_identity(self, values: dict[str, Any]) -> dict:
        data = self._read()
        identity = dict(data.get("identity") or {})
        for key in ("name", "email", "phone", "location"):
            if key in values:
                identity[key] = str(values.get(key) or "").strip()[:300]
        data["identity"] = identity
        self._write(data)
        return {**(data.get("profile") or {}), **identity}

    def resume_studio(self) -> dict | None:
        value = self._read().get("resume_studio")
        return value if isinstance(value, dict) else None

    def save_resume_studio(self, value: dict[str, Any]) -> dict:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 2_000_000:
            raise ValueError("Resume draft is too large to save")
        data = self._read()
        data["resume_studio"] = value
        self._write(data)
        return value

    def save_profile(self, analysis: dict) -> dict:
        profile = {key: value for key, value in analysis.items() if key in PROFILE_FIELDS}
        data = self._read()
        data["profile"] = profile
        self._write(data)
        return {**profile, **(data.get("identity") or {})}

    def save_resume(self, content: bytes, original_name: str) -> dict:
        """Keep one private, replaceable copy of the user's current resume."""
        safe_name = Path(str(original_name or "resume").replace("\\", "/")).name[:180] or "resume"
        extension = Path(safe_name).suffix.lower()
        if extension not in {".pdf", ".docx", ".txt"}:
            raise ValueError("Only PDF, DOCX, and TXT files are supported")
        stored_name = f"resume-{uuid4().hex}{extension}"
        if self.database:
            content_type = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".txt": "text/plain; charset=utf-8"}[extension]
            self.database.write_file(stored_name, safe_name, content_type, content)
            data = self._read()
            previous = data.get("resume") or {}
            data["resume"] = {"original_name": safe_name, "stored_name": stored_name, "size_bytes": len(content), "saved_at": datetime.now(timezone.utc).isoformat()}
            try:
                self._write(data)
            except Exception:
                self.database.delete_file(stored_name)
                raise
            previous_name = previous.get("stored_name")
            if previous_name and previous_name != stored_name:
                self.database.delete_file(previous_name)
            return self.resume_info()

        self.resume_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary_path = tempfile.mkstemp(prefix=".resume-", suffix=extension, dir=str(self.resume_directory))
        target = self.resume_directory / stored_name
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            os.replace(temporary_path, target)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

        data = self._read()
        previous = data.get("resume") or {}
        metadata = {
            "original_name": safe_name,
            "stored_name": stored_name,
            "size_bytes": len(content),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        data["resume"] = metadata
        try:
            self._write(data)
        except Exception:
            target.unlink(missing_ok=True)
            raise

        previous_name = previous.get("stored_name")
        if previous_name and previous_name != stored_name and Path(previous_name).name == previous_name:
            (self.resume_directory / previous_name).unlink(missing_ok=True)
        return self.resume_info()

    def resume_info(self) -> dict | None:
        resume = self._read().get("resume")
        if not isinstance(resume, dict):
            return None
        stored_name = str(resume.get("stored_name") or "")
        if not stored_name or Path(stored_name).name != stored_name:
            return None
        if self.database:
            if not self.database.file_exists(stored_name):
                return None
        elif not (self.resume_directory / stored_name).is_file():
            return None
        return {key: resume[key] for key in ("original_name", "size_bytes", "saved_at") if key in resume}

    def resume_path(self) -> Path | None:
        if self.database:
            return None
        resume = self._read().get("resume") or {}
        stored_name = str(resume.get("stored_name") or "")
        if not stored_name or Path(stored_name).name != stored_name:
            return None
        path = self.resume_directory / stored_name
        return path if path.is_file() else None

    def resume_file(self) -> tuple[str, str, bytes] | None:
        """Return the saved original resume, independent of its storage backend."""
        resume = self._read().get("resume") or {}
        stored_name = str(resume.get("stored_name") or "")
        if not stored_name or Path(stored_name).name != stored_name:
            return None
        if self.database:
            return self.database.read_file(stored_name)
        path = self.resume_directory / stored_name
        if not path.is_file():
            return None
        extension = path.suffix.lower()
        content_type = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".txt": "text/plain; charset=utf-8"}.get(extension, "application/octet-stream")
        return str(resume.get("original_name") or "resume"), content_type, path.read_bytes()

    def preferences(self) -> dict:
        return {key: value for key, value in self._read().get("preferences", {}).items() if not key.startswith("_")}

    def save_preferences(self, values: dict[str, Any]) -> dict:
        current = self._read()
        cleaned = {}
        for key in PREFERENCE_FIELDS:
            value = values.get(key)
            if value is None:
                continue
            if key == "min_salary":
                try:
                    value = max(0, float(value))
                except (TypeError, ValueError):
                    continue
            elif key == "digest_frequency":
                value = str(value).lower()
                if value not in {"off", "weekly"}:
                    continue
            else:
                value = str(value).strip()[:500]
            cleaned[key] = value
        if current.get("preferences", {}).get("_digest_last_checked"):
            cleaned["_digest_last_checked"] = current["preferences"]["_digest_last_checked"]
        current["preferences"] = cleaned
        self._write(current)
        return cleaned

    def roles(self, include_archived: bool = False) -> list[dict]:
        roles = self._read().get("roles", [])
        return roles if include_archived else [role for role in roles if role.get("status") != "archived"]

    def save_role(self, role: dict) -> tuple[dict, bool]:
        data = self._read()
        url = str(role.get("url") or "").strip()
        existing = next((item for item in data["roles"] if item.get("url") == url), None)
        if existing:
            return existing, False
        record = {
            "id": str(uuid4()),
            "title": str(role.get("title") or "Opportunity")[:250],
            "url": url,
            "source": str(role.get("source") or "")[:160],
            "company": str(role.get("company") or "")[:200],
            "location": str(role.get("location") or "")[:200],
            "snippet": str(role.get("snippet") or "")[:1200],
            "salary": str(role.get("salary") or "")[:120],
            "work_mode": str(role.get("work_mode") or "")[:80],
            "employment_type": str(role.get("employment_type") or "")[:100],
            "fit_score": role.get("fit_score"),
            "fit_reasons": role.get("fit_reasons") or [],
            "matched_skills": role.get("matched_skills") or [],
            "missing_skills": role.get("missing_skills") or [],
            "status": "saved",
            "note": "",
            "follow_up_on": "",
            "saved_at": role.get("found_at") or "",
            "updated_at": role.get("found_at") or "",
        }
        data["roles"].insert(0, record)
        self._write(data)
        return record, True

    def update_role(self, role_id: str, changes: dict) -> dict | None:
        data = self._read()
        for role in data["roles"]:
            if role.get("id") != role_id:
                continue
            status = changes.get("status", role.get("status", "saved"))
            if status not in ROLE_STATUSES:
                raise ValueError("Status must be saved, applied, interview, rejected, offer, or archived")
            role["status"] = status
            role["note"] = str(changes.get("note", role.get("note", "")) or "")[:2000]
            role["follow_up_on"] = str(changes.get("follow_up_on", role.get("follow_up_on", "")) or "")[:10]
            role["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write(data)
            return role
        return None

    def digest_urls(self) -> set[str]:
        return set(self._read().get("digest_urls", []))

    def remember_digest(self, urls: list[str]) -> None:
        data = self._read()
        values = list(dict.fromkeys([*urls, *data.get("digest_urls", [])]))[:1000]
        data["digest_urls"] = values
        self._write(data)

    def save_latest_digest(self, query: str, results: list[dict]) -> None:
        data = self._read()
        data["last_digest"] = {"query": query, "results": results[:15], "created_at": datetime.now(timezone.utc).isoformat()}
        self._write(data)

    def last_digest(self) -> dict | None:
        return self._read().get("last_digest")

    def mark_digest_checked(self) -> None:
        data = self._read()
        data.setdefault("preferences", {})["_digest_last_checked"] = datetime.now(timezone.utc).isoformat()
        self._write(data)

    def digest_last_checked(self) -> str:
        return str(self._read().get("preferences", {}).get("_digest_last_checked") or "")
