"""Verify that the target DB is already managed from the Alembic baseline."""

from __future__ import annotations

import os
import sys
from typing import Iterable

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine


BASELINE_REVISION = "baseline_20260701"


def normalize_database_url(database_url: str) -> str:
    """Convert async SQLAlchemy URLs to a sync driver URL for Alembic checks."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def revision_includes_baseline(
    script: ScriptDirectory,
    current_revision: str,
    baseline_revision: str = BASELINE_REVISION,
) -> bool:
    if current_revision == baseline_revision:
        return True

    try:
        revisions = script.iterate_revisions(current_revision, baseline_revision)
        return any(
            revision.revision == baseline_revision
            or down_revision_includes(
                getattr(revision, "down_revision", None),
                baseline_revision,
            )
            for revision in revisions
        )
    except Exception:
        return False


def down_revision_includes(down_revision: object, baseline_revision: str) -> bool:
    if down_revision is None:
        return False

    if isinstance(down_revision, str):
        return down_revision == baseline_revision

    if isinstance(down_revision, (tuple, list, set)):
        return baseline_revision in down_revision

    return False


def validate_current_heads(
    current_heads: Iterable[str],
    script: ScriptDirectory,
    baseline_revision: str = BASELINE_REVISION,
) -> tuple[str, ...]:
    heads = tuple(current_heads)
    if not heads:
        raise RuntimeError(
            "Alembic current revision is empty. "
            f"Stamp the verified DB to {baseline_revision} before running CD."
        )

    invalid_heads = [
        revision
        for revision in heads
        if not revision_includes_baseline(script, revision, baseline_revision)
    ]
    if invalid_heads:
        invalid = ", ".join(invalid_heads)
        raise RuntimeError(
            "Alembic baseline check failed. "
            f"Current revision(s) [{invalid}] are not at or after "
            f"{baseline_revision}. Verify the schema and run one-time "
            f"`alembic stamp {baseline_revision}` before enabling CD migration."
        )

    return heads


def get_current_heads(database_url: str, alembic_config_path: str) -> tuple[str, ...]:
    engine = create_engine(normalize_database_url(database_url))
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return tuple(context.get_current_heads())


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required for Alembic baseline check.", file=sys.stderr)
        return 2

    baseline_revision = os.getenv("ALEMBIC_BASELINE_REVISION", BASELINE_REVISION)
    alembic_config_path = os.getenv("ALEMBIC_CONFIG", "alembic.ini")
    script = ScriptDirectory.from_config(Config(alembic_config_path))

    try:
        current_heads = get_current_heads(database_url, alembic_config_path)
        validated_heads = validate_current_heads(
            current_heads,
            script,
            baseline_revision,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        "Alembic baseline check passed: "
        f"current={','.join(validated_heads)} baseline={baseline_revision}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
