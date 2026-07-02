from types import SimpleNamespace

import pytest

from scripts.alembic_baseline_guard import (
    BASELINE_REVISION,
    normalize_database_url,
    revision_includes_baseline,
    validate_current_heads,
)


class FakeScript:
    def __init__(self, chains):
        self.chains = chains

    def iterate_revisions(self, current_revision, baseline_revision):
        chain = self.chains.get((current_revision, baseline_revision))
        if chain is None:
            raise ValueError("unknown revision chain")
        return [SimpleNamespace(revision=revision) for revision in chain]


class LazyFailScript:
    def iterate_revisions(self, current_revision, baseline_revision):
        def fail_on_iteration():
            raise ValueError("not an ancestor")
            yield

        return fail_on_iteration()


def test_normalize_database_url_converts_asyncpg_url():
    url = "postgresql+asyncpg://user:pass@example.com/db"

    assert normalize_database_url(url) == "postgresql://user:pass@example.com/db"


def test_revision_includes_baseline_accepts_exact_baseline():
    script = FakeScript({})

    assert revision_includes_baseline(script, BASELINE_REVISION)


def test_validate_current_heads_accepts_revision_after_baseline():
    script = FakeScript(
        {
            ("future_revision", BASELINE_REVISION): [
                "future_revision",
                BASELINE_REVISION,
            ]
        }
    )

    assert validate_current_heads(["future_revision"], script) == ("future_revision",)


def test_validate_current_heads_rejects_revision_before_baseline():
    script = FakeScript({})

    with pytest.raises(RuntimeError, match="not at or after baseline_20260701"):
        validate_current_heads(["n3o4p5q6r7s8"], script)


def test_validate_current_heads_rejects_lazy_revision_lookup_error():
    script = LazyFailScript()

    with pytest.raises(RuntimeError, match="not at or after baseline_20260701"):
        validate_current_heads(["m2n3o4p5q6r7"], script)


def test_validate_current_heads_rejects_empty_current():
    script = FakeScript({})

    with pytest.raises(RuntimeError, match="current revision is empty"):
        validate_current_heads([], script)
