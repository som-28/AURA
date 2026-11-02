"""Transfer the single-user Neon data namespace to a signed-in Clerk subject."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env.local")
load_dotenv(ROOT / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to-user-id", required=True, help="Verified Clerk subject from GET /auth/me")
    args = parser.parse_args()

    from_owner = os.getenv("AURA_USER_ID", "single-user").strip()
    to_owner = args.to_user_id.strip()
    if not to_owner.startswith("user_") or to_owner == from_owner:
        parser.error("--to-user-id must be a Clerk user ID different from AURA_USER_ID")

    dsn = (os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not dsn:
        parser.error("Set DATABASE_URL or NEON_DATABASE_URL first")

    import psycopg

    with psycopg.connect(dsn) as connection:
        state_target = connection.execute(
            "SELECT count(*) FROM aura_state WHERE owner_id = %s", (to_owner,)
        ).fetchone()[0]
        files_target = connection.execute(
            "SELECT count(*) FROM aura_files WHERE owner_id = %s", (to_owner,)
        ).fetchone()[0]
        if state_target or files_target:
            parser.error("The Clerk user already has Neon data; refusing to merge or overwrite it")

        moved_state = connection.execute(
            "UPDATE aura_state SET owner_id = %s WHERE owner_id = %s RETURNING namespace",
            (to_owner, from_owner),
        ).fetchall()
        moved_files = connection.execute(
            "UPDATE aura_files SET owner_id = %s WHERE owner_id = %s RETURNING file_key",
            (to_owner, from_owner),
        ).fetchall()

    print(f"Transferred {len(moved_state)} state records and {len(moved_files)} files to the verified Clerk user.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
