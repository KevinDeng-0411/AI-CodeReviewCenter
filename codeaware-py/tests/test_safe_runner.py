"""C1-D runner orchestration and cleanup behavior."""

import signal
import subprocess

import pytest

import run_tests_safe


@pytest.fixture
def deterministic_runner(monkeypatch):
    ports = iter([35432, 36379])
    tokens = iter(["abc12345abc12345", "runner-auth"])
    monkeypatch.setattr(run_tests_safe, "_free_port", lambda: next(ports))
    monkeypatch.setattr(run_tests_safe.secrets, "token_hex", lambda _size: next(tokens))
    def close_coroutine(awaitable):
        awaitable.close()
        return None

    monkeypatch.setattr(run_tests_safe.asyncio, "run", close_coroutine)
    monkeypatch.setattr(run_tests_safe, "_wait_redis", lambda *_args: None)


def test_cleanup_runs_when_compose_up_fails(deterministic_runner, monkeypatch):
    calls = []

    def compose(_stack_id, *args, **_kwargs):
        calls.append(args)
        if args[:2] == ("up", "-d"):
            raise subprocess.CalledProcessError(1, ["docker", "compose", "up"])
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(run_tests_safe, "_compose", compose)
    assert run_tests_safe.run(["-q"]) == 1
    assert ("down", "-v", "--remove-orphans") in calls


def test_test_failure_is_preserved_after_successful_cleanup(
    deterministic_runner, monkeypatch
):
    monkeypatch.setattr(
        run_tests_safe,
        "_compose",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "", ""),
    )
    monkeypatch.setattr(
        run_tests_safe.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 7, "", ""),
    )
    assert run_tests_safe.run(["-q"]) == 7


def test_cleanup_failure_forces_nonzero(deterministic_runner, monkeypatch):
    def compose(_stack_id, *args, **_kwargs):
        return subprocess.CompletedProcess([], 1 if args[0] == "down" else 0, "", "")

    monkeypatch.setattr(run_tests_safe, "_compose", compose)
    monkeypatch.setattr(
        run_tests_safe.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "", ""),
    )
    assert run_tests_safe.run(["-q"]) == 1


def test_signal_handler_turns_sigterm_into_controlled_interrupt():
    with pytest.raises(run_tests_safe.RunnerInterrupted, match=str(signal.SIGTERM)):
        run_tests_safe._raise_interrupted(signal.SIGTERM, None)
