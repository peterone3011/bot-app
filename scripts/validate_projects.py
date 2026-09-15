from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import ConfigError, enabled_project_slugs, load_projects


def _enabled_features(config) -> str:
    return ",".join(
        name for name, enabled in vars(config.features).items() if enabled
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Validate project configuration without starting external services."
    )
    parser.add_argument(
        "--projects",
        help="Comma-separated project slugs; defaults to ENABLED_PROJECTS.",
    )
    args = parser.parse_args(argv)
    values = os.environ if environ is None else environ
    root = repo_root or REPO_ROOT
    try:
        slugs = (
            tuple(item.strip() for item in args.projects.split(",") if item.strip())
            if args.projects is not None
            else enabled_project_slugs(values)
        )
        configs = load_projects(root, slugs, values)
    except ConfigError as exc:
        print(f"INVALID {exc}")
        return 2
    for config in configs:
        print(
            f"OK {config.slug} guild={config.discord.guild_id} "
            f"features={_enabled_features(config)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
