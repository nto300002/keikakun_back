"""Run one Alembic command against the paired main/test database URLs."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Sequence

import dotenv


dotenv.load_dotenv()


@dataclass(frozen=True)
class Target:
    name: str
    env_var: str


TARGETS_BY_ENV = {
    "local": (
        Target(name="DEV_DATABASE_URL", env_var="DEV_DATABASE_URL"),
        Target(name="DEV_TEST_DATABASE_URL", env_var="DEV_TEST_DATABASE_URL"),
    ),
    "prod": (
        Target(name="PROD_DATABASE_URL", env_var="PROD_DATABASE_URL"),
        Target(name="PROD_TEST_DATABASE_URL", env_var="PROD_TEST_DATABASE_URL"),
    ),
}


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an Alembic command against a main/test DB pair.",
    )
    parser.add_argument(
        "--env",
        required=True,
        choices=sorted(TARGETS_BY_ENV),
        help="Target DB pair to use.",
    )
    parser.add_argument(
        "alembic_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to alembic, for example: upgrade head",
    )
    args = parser.parse_args(argv)
    if not args.alembic_args:
        parser.error("alembic arguments are required")
    return args


def run_for_target(target: Target, alembic_args: Sequence[str]) -> int:
    database_url = os.getenv(target.env_var)
    if not database_url:
        print(f"{target.env_var} is required.", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    print(f"Running alembic for {target.name}: alembic {' '.join(alembic_args)}")
    completed = subprocess.run(["alembic", *alembic_args], env=env, check=False)
    if completed.returncode != 0:
        print(
            f"Alembic failed for {target.name} with exit code {completed.returncode}.",
            file=sys.stderr,
        )
    return completed.returncode


def run_pair(mode: str, alembic_args: Sequence[str]) -> int:
    for target in TARGETS_BY_ENV[mode]:
        result = run_for_target(target, alembic_args)
        if result != 0:
            return result
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return run_pair(args.env, args.alembic_args)


if __name__ == "__main__":
    raise SystemExit(main())
