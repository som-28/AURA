"""Local persistence for AURA World missions and collected artifacts."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from src.agent.state_store import get_database_backend


CATEGORIES = {"making", "learning", "discovery", "writing", "design", "life"}


class WorldStore:
    def __init__(self, path: str | None = None):
        self.path = Path(path or os.getenv("AURA_WORLD_STORE", ".aura_world.json"))
        self.database = get_database_backend() if path is None else None

    def _read(self) -> dict:
        if self.database:
            value = self.database.read_state("world", {})
            if not isinstance(value, dict):
                value = {}
            value.setdefault("missions", [])
            value.setdefault("artifacts", [])
            value.setdefault("discoveries", [])
            return value
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                value.setdefault("missions", [])
                value.setdefault("artifacts", [])
                value.setdefault("discoveries", [])
                return value
        except (OSError, json.JSONDecodeError):
            pass
        return {"missions": [], "artifacts": [], "discoveries": []}

    def _write(self, data: dict) -> None:
        if self.database:
            self.database.write_state("world", data)
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

    def snapshot(self) -> dict:
        data = self._read()
        missions = data["missions"]
        artifacts = data["artifacts"]
        discoveries = data["discoveries"]
        activity = {category: 0 for category in CATEGORIES}
        for item in discoveries:
            for category in item.get("categories") or [item.get("category")]:
                if category in activity:
                    activity[category] += 1
        # Old mission/artifact records are intentionally left intact for compatibility,
        # but the curiosity world grows only from actual portal discoveries.
        points = len(discoveries)
        ranks = [(0, "New spark"), (2, "Curious"), (5, "Explorer"), (10, "Wayfinder"), (18, "Worldbuilder")]
        rank_index = max(index for index, (threshold, _) in enumerate(ranks) if points >= threshold)
        rank = ranks[rank_index][1]
        next_rank = ranks[rank_index + 1][0] if rank_index + 1 < len(ranks) else None
        return {
            "missions": missions,
            "artifacts": artifacts,
            "discoveries": discoveries,
            "counts": {"discoveries": len(discoveries), "worlds": sum(count > 0 for count in activity.values()), "completed": sum(item.get("status") == "completed" for item in missions), "artifacts": len(artifacts), "points": points},
            "activity": activity,
            "companion": {"name": "Mote", "rank": rank, "points": points, "next_rank_at": next_rank},
        }

    def add_discovery(self, title: str, category: str, choice: str, insight: str, categories: list[str] | None = None) -> dict:
        data = self._read()
        linked_categories = list(dict.fromkeys(categories or [category]))
        discovery = {"id": str(uuid4()), "title": title.strip()[:140], "category": category, "categories": linked_categories, "choice": choice.strip()[:200], "insight": insight.strip()[:1200], "created_at": datetime.now(timezone.utc).isoformat()}
        data["discoveries"].insert(0, discovery)
        data["discoveries"] = data["discoveries"][:200]
        self._write(data)
        return discovery

    def add_mission(self, title: str, category: str, note: str) -> dict:
        data = self._read()
        mission = {"id": str(uuid4()), "title": title.strip()[:140], "category": category, "note": note.strip()[:800], "status": "active", "created_at": datetime.now(timezone.utc).isoformat(), "completed_at": ""}
        data["missions"].insert(0, mission)
        self._write(data)
        return mission

    def complete_mission(self, mission_id: str) -> dict | None:
        data = self._read()
        for mission in data["missions"]:
            if mission["id"] == mission_id:
                mission["status"] = "completed"
                mission["completed_at"] = datetime.now(timezone.utc).isoformat()
                self._write(data)
                return mission
        return None

    def add_artifact(self, title: str, category: str, content: str, url: str) -> dict:
        data = self._read()
        artifact = {"id": str(uuid4()), "title": title.strip()[:140], "category": category, "content": content.strip()[:5000], "url": url.strip()[:1000], "created_at": datetime.now(timezone.utc).isoformat()}
        data["artifacts"].insert(0, artifact)
        self._write(data)
        return artifact
