import subprocess

import pytest

from scripts.run_alembic_for_pair import main


def test_local_runs_dev_then_dev_test(monkeypatch):
    calls = []

    def fake_run(command, env, check):
        calls.append((command, env["DATABASE_URL"], check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("DEV_DATABASE_URL", "postgresql://dev-secret")
    monkeypatch.setenv("DEV_TEST_DATABASE_URL", "postgresql://dev-test-secret")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = main(["--env", "local", "upgrade", "head"])

    assert result == 0
    assert calls == [
        (["alembic", "upgrade", "head"], "postgresql://dev-secret", False),
        (["alembic", "upgrade", "head"], "postgresql://dev-test-secret", False),
    ]


def test_prod_runs_prod_then_prod_test(monkeypatch):
    calls = []

    def fake_run(command, env, check):
        calls.append(env["DATABASE_URL"])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("PROD_DATABASE_URL", "postgresql://prod-secret")
    monkeypatch.setenv("PROD_TEST_DATABASE_URL", "postgresql://prod-test-secret")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = main(["--env", "prod", "upgrade", "head"])

    assert result == 0
    assert calls == ["postgresql://prod-secret", "postgresql://prod-test-secret"]


def test_stops_before_second_database_when_first_fails(monkeypatch):
    calls = []

    def fake_run(command, env, check):
        calls.append(env["DATABASE_URL"])
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setenv("DEV_DATABASE_URL", "postgresql://dev-secret")
    monkeypatch.setenv("DEV_TEST_DATABASE_URL", "postgresql://dev-test-secret")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = main(["--env", "local", "upgrade", "head"])

    assert result == 1
    assert calls == ["postgresql://dev-secret"]


def test_second_database_failure_returns_non_zero(monkeypatch):
    calls = []

    def fake_run(command, env, check):
        calls.append(env["DATABASE_URL"])
        return subprocess.CompletedProcess(command, 0 if len(calls) == 1 else 3)

    monkeypatch.setenv("DEV_DATABASE_URL", "postgresql://dev-secret")
    monkeypatch.setenv("DEV_TEST_DATABASE_URL", "postgresql://dev-test-secret")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = main(["--env", "local", "upgrade", "head"])

    assert result == 3
    assert calls == ["postgresql://dev-secret", "postgresql://dev-test-secret"]


def test_missing_url_returns_configuration_error(monkeypatch):
    monkeypatch.delenv("DEV_DATABASE_URL", raising=False)
    monkeypatch.setenv("DEV_TEST_DATABASE_URL", "postgresql://dev-test-secret")

    assert main(["--env", "local", "upgrade", "head"]) == 2


def test_does_not_log_database_urls(monkeypatch, capsys):
    def fake_run(command, env, check):
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("PROD_DATABASE_URL", "postgresql://prod-secret")
    monkeypatch.setenv("PROD_TEST_DATABASE_URL", "postgresql://prod-test-secret")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = main(["--env", "prod", "upgrade", "head"])

    captured = capsys.readouterr()
    assert result == 0
    assert "postgresql://prod-secret" not in captured.out
    assert "postgresql://prod-test-secret" not in captured.out
    assert "PROD_DATABASE_URL" in captured.out
    assert "PROD_TEST_DATABASE_URL" in captured.out


def test_requires_alembic_args():
    with pytest.raises(SystemExit):
        main(["--env", "local"])
