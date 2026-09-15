"""
The auth token is the only thing standing between "local dev tool" and
"anyone who read your repo can place orders". These tests pin the behaviour:

  * a token copied from .env.example must be rejected;
  * a real generated token must be accepted;
  * the generator writes the SAME value into both files.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.config  # noqa: E402
from tools import setup_env  # noqa: E402


def _settings(token: str) -> core.config.Settings:
    return core.config.Settings(auth_token=token)


@pytest.mark.parametrize("token", [
    "", "change-me", "dev-local-token-change-me",
    "omniquant-local-dev-token",   # the value that used to sit in .env.example
    "YOUR-TOKEN-HERE", "token", "secret", "short",
])
def test_placeholder_and_short_tokens_are_rejected(token):
    s = _settings(token)
    assert s.auth_configured is False
    assert s.auth_weakness is not None


def test_generated_token_is_accepted():
    token = setup_env.generate_token()
    assert len(token) >= 32
    s = _settings(token)
    assert s.auth_configured is True
    assert s.auth_weakness is None


def test_generated_tokens_are_unique():
    assert len({setup_env.generate_token() for _ in range(50)}) == 50


def test_read_write_env_round_trip(tmp_path):
    example = tmp_path / ".env.example"
    example.write_text(
        "# a comment\n"
        "TRADING_MODE=paper\n"
        "\n"
        "# Must match the frontend\n"
        "AUTH_TOKEN=\n",
        encoding="utf-8",
    )
    target = tmp_path / ".env"

    values = setup_env.read_env(example)
    assert values["TRADING_MODE"] == "paper"
    assert values["AUTH_TOKEN"] == ""

    values["AUTH_TOKEN"] = "abc123"
    setup_env.write_env(target, example, values)
    text = target.read_text(encoding="utf-8")

    assert "AUTH_TOKEN=abc123" in text
    assert "# a comment" in text            # comments survive
    assert setup_env.read_env(target)["AUTH_TOKEN"] == "abc123"


def test_setup_writes_the_same_token_to_both_files(tmp_path, monkeypatch):
    backend_env = tmp_path / "backend" / ".env"
    frontend_env = tmp_path / "frontend" / ".env.local"
    monkeypatch.setattr(setup_env, "BACKEND_ENV", backend_env)
    monkeypatch.setattr(setup_env, "FRONTEND_ENV", frontend_env)
    monkeypatch.setattr(setup_env, "BACKEND_EXAMPLE",
                        Path(__file__).resolve().parents[2] / "backend" / ".env.example")
    monkeypatch.setattr(setup_env, "FRONTEND_EXAMPLE",
                        Path(__file__).resolve().parents[2] / "frontend" / ".env.example")

    assert setup_env.main([]) == 0

    backend = setup_env.read_env(backend_env)
    frontend = setup_env.read_env(frontend_env)
    assert backend["AUTH_TOKEN"] == frontend["NEXT_PUBLIC_AUTH_TOKEN"]
    assert len(backend["AUTH_TOKEN"]) >= 32


def test_setup_is_idempotent_without_force(tmp_path, monkeypatch):
    backend_env = tmp_path / "backend" / ".env"
    frontend_env = tmp_path / "frontend" / ".env.local"
    monkeypatch.setattr(setup_env, "BACKEND_ENV", backend_env)
    monkeypatch.setattr(setup_env, "FRONTEND_ENV", frontend_env)
    monkeypatch.setattr(setup_env, "BACKEND_EXAMPLE",
                        Path(__file__).resolve().parents[2] / "backend" / ".env.example")
    monkeypatch.setattr(setup_env, "FRONTEND_EXAMPLE",
                        Path(__file__).resolve().parents[2] / "frontend" / ".env.example")

    setup_env.main([])
    first = setup_env.read_env(backend_env)["AUTH_TOKEN"]
    setup_env.main([])                       # no --force
    assert setup_env.read_env(backend_env)["AUTH_TOKEN"] == first


def test_force_rotates_the_token(tmp_path, monkeypatch):
    backend_env = tmp_path / "backend" / ".env"
    frontend_env = tmp_path / "frontend" / ".env.local"
    monkeypatch.setattr(setup_env, "BACKEND_ENV", backend_env)
    monkeypatch.setattr(setup_env, "FRONTEND_ENV", frontend_env)
    monkeypatch.setattr(setup_env, "BACKEND_EXAMPLE",
                        Path(__file__).resolve().parents[2] / "backend" / ".env.example")
    monkeypatch.setattr(setup_env, "FRONTEND_EXAMPLE",
                        Path(__file__).resolve().parents[2] / "frontend" / ".env.example")

    setup_env.main([])
    first = setup_env.read_env(backend_env)["AUTH_TOKEN"]
    setup_env.main(["--force"])
    second = setup_env.read_env(backend_env)["AUTH_TOKEN"]
    assert first != second
