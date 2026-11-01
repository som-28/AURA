"""Small atomic JSON store for inspectable execution records."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


class RunStore:
    def __init__(self, path: str | None = None):
        self.path = Path(path or os.getenv("AURA_RUN_STORE", ".aura_runs.json"))

    def _read(self) -> Dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, records: Dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_path = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            dir=str(self.path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(records, handle, indent=2)
                handle.write("\n")
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def save(self, record: dict) -> dict:
        run_id = str(record["run_id"])
        records = self._read()
        records[run_id] = record
        self._write(records)
        return record

    def get(self, run_id: str) -> Optional[dict]:
        return self._read().get(run_id)

    def list(self) -> List[dict]:
        records = list(self._read().values())
        return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)

    def metrics(self) -> dict:
        records = self.list()
        completed = sum(record.get("status") == "completed" for record in records)
        partial = sum(record.get("status") == "partial" for record in records)
        failed = sum(record.get("status") == "failed" for record in records)
        return {
            "total_runs": len(records),
            "completed_runs": completed,
            "partial_runs": partial,
            "failed_runs": failed,
            "success_rate": completed / len(records) if records else 0.0,
        }
