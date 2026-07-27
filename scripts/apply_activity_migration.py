from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MIGRATION = (
    ROOT / "supabase" / "migrations" / "20260727_activity_campaigns.sql"
)


def _postgres_environment(database_url: str) -> dict[str, str]:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise ValueError("SUPABASE_DB_URL must be a PostgreSQL connection URL")

    env = os.environ.copy()
    env.update(
        {
            "PGHOST": parsed.hostname,
            "PGPORT": str(parsed.port or 5432),
            "PGDATABASE": unquote(parsed.path.lstrip("/") or "postgres"),
            "PGUSER": unquote(parsed.username or "postgres"),
            "PGPASSWORD": unquote(parsed.password or ""),
            "PGSSLMODE": "require",
        }
    )
    return env


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply the Discord activity migration with psql."
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("SUPABASE_DB_URL"),
        help="PostgreSQL URL; defaults to SUPABASE_DB_URL.",
    )
    args = parser.parse_args()

    if not args.database_url:
        parser.error("--database-url or SUPABASE_DB_URL is required")
    if not DEFAULT_MIGRATION.is_file():
        parser.error(f"migration not found: {DEFAULT_MIGRATION}")
    if shutil.which("psql") is None:
        parser.error("psql is required but was not found on PATH")

    subprocess.run(
        [
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(DEFAULT_MIGRATION),
        ],
        check=True,
        env=_postgres_environment(args.database_url),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
