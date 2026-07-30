"""C3-A release version and environment contract freeze."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from app.core.config import Settings
from app.core.version import APP_VERSION
from app.main import app

APP_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_ROOT.parent


def _env_example_keys() -> set[str]:
    keys: set[str] = set()
    for raw_line in (APP_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, _ = line.partition("=")
        assert separator, f"invalid .env.example line: {raw_line!r}"
        assert key and key == key.upper()
        assert key not in keys
        keys.add(key)
    return keys


def test_release_version_is_consistent_across_backend_frontend_and_openapi():
    pyproject = tomllib.loads((APP_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    frontend = json.loads((APP_ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    frontend_lock = json.loads(
        (APP_ROOT / "frontend/package-lock.json").read_text(encoding="utf-8")
    )
    snapshot = json.loads(
        (APP_ROOT / "openapi/current-release.json").read_text(encoding="utf-8")
    )

    assert pyproject["project"]["version"] == APP_VERSION
    assert app.version == APP_VERSION
    assert snapshot["info"]["version"] == APP_VERSION
    assert frontend["version"] == APP_VERSION
    assert frontend_lock["version"] == APP_VERSION
    assert frontend_lock["packages"][""]["version"] == APP_VERSION


def test_env_example_exactly_documents_supported_settings():
    expected = {field.upper() for field in Settings.model_fields}
    assert _env_example_keys() == expected


def test_env_example_contains_placeholder_not_a_real_key():
    content = (APP_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "LLM_API_KEY=sk-your-deepseek-api-key" in content
    assert "LOCAL_PROJECT_ROOTS=[]" in content
    assert str(REPO_ROOT) not in content
