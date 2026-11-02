"""Copy local AURA JSON stores and the current resume into Neon PostgreSQL.

Configure AURA_STORAGE_BACKEND=neon and NEON_DATABASE_URL first. This script
never deletes or edits local source files and skips existing database rows.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from src.agent.state_store import get_database_backend  # noqa: E402


STORE_FILES = {
    "career": os.getenv("AURA_CAREER_STORE", ".aura_career.json"),
    "runs": os.getenv("AURA_RUN_STORE", ".aura_runs.json"),
    "memory": os.getenv("AURA_MEMORY_STORE", "agent_memory.json"),
    "world": os.getenv("AURA_WORLD_STORE", ".aura_world.json"),
}
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain; charset=utf-8",
}


def main() -> int:
    if os.getenv("AURA_STORAGE_BACKEND", "").strip().lower() != "neon":
        print("Set AURA_STORAGE_BACKEND=neon before running this migration.", file=sys.stderr)
        return 2
    backend = get_database_backend()
    assert backend is not None

    imported = []
    skipped = []
    for namespace, configured_path in STORE_FILES.items():
        source_path = Path(configured_path)
        if not source_path.is_file():
            skipped.append(namespace)
            continue
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"Could not read {source_path}: {error}", file=sys.stderr)
            return 1
        if namespace == "career":
            resume = data.get("resume") if isinstance(data, dict) else None
            if isinstance(resume, dict):
                stored_name = str(resume.get("stored_name") or "")
                if stored_name and Path(stored_name).name == stored_name:
                    resume_dir = source_path.parent / f"{source_path.stem}_files"
                    resume_path = resume_dir / stored_name
                    if resume_path.is_file():
                        extension = resume_path.suffix.lower()
                        backend.write_file(
                            stored_name,
                            str(resume.get("original_name") or "resume"),
                            CONTENT_TYPES.get(extension, "application/octet-stream"),
                            resume_path.read_bytes(),
                        )

        if backend.write_state_if_absent(namespace, data):
            imported.append(namespace)
        else:
            skipped.append(namespace)

    print(f"Imported namespaces: {', '.join(imported) if imported else 'none'}")
    print(f"Skipped missing/already-present namespaces: {', '.join(skipped) if skipped else 'none'}")
    print("Local source files were left unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
