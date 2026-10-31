"""Persistent atomic JSON-backed memory manager.

Provides structured long-term state, user preferences, and execution context
across agent runs.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


class Memory:
    def __init__(self, path: str | None = None):
        self.path = Path(path or os.getenv("AURA_MEMORY_STORE", "agent_memory.json"))
        if not self.path.exists():
            self._write({
                "preferences": {},
                "context": {},
                "recent_runs": []
            })

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"preferences": {}, "context": {}, "recent_runs": []}
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                content.setdefault("preferences", {})
                content.setdefault("context", {})
                content.setdefault("recent_runs", [])
                return content
            return {"preferences": {}, "context": {}, "recent_runs": []}
        except (OSError, json.JSONDecodeError):
            return {"preferences": {}, "context": {}, "recent_runs": []}

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_path = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            dir=str(self.path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
                handle.write("\n")
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

    def get(self, key: str, default: Any = None) -> Any:
        data = self._read()
        return data.get("context", {}).get(key, data.get(key, default))

    def set(self, key: str, value: Any) -> None:
        data = self._read()
        data.setdefault("context", {})[key] = value
        self._write(data)

    def get_preferences(self) -> Dict[str, Any]:
        return dict(self._read().get("preferences", {}))

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self._read().get("preferences", {}).get(key, default)

    def set_preference(self, key: str, value: Any) -> None:
        data = self._read()
        data.setdefault("preferences", {})[key] = value
        self._write(data)

    def record_run(self, run_id: str, goal: str, status: str, summary: Optional[str] = None) -> None:
        data = self._read()
        recent = data.setdefault("recent_runs", [])
        entry = {
            "run_id": run_id,
            "goal": goal,
            "status": status,
            "summary": summary,
        }
        # Keep latest 20 runs
        recent.insert(0, entry)
        data["recent_runs"] = recent[:20]
        self._write(data)

    def get_recent_runs(self, limit: int = 5) -> List[dict]:
        runs = self._read().get("recent_runs", [])
        return runs[:limit]

    def clear(self) -> None:
        self._write({"preferences": {}, "context": {}, "recent_runs": []})

    def to_dict(self) -> Dict[str, Any]:
        return self._read()
