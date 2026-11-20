import os
from pathlib import Path

import pytest

from app.config import export_provider_keys


def test_only_provider_keys_are_exported_and_real_env_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "GEMINI_API_KEY=from-file\n"
        "OPENAI_API_KEY=file-openai\n"
        "OPENAI_API_BASE=http://example.test\n"
        "APORIA_MODEL_FAST=should-not-be-exported\n"
        "EMPTY_API_KEY=\n"
    )
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("APORIA_MODEL_FAST", raising=False)
    monkeypatch.delenv("EMPTY_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "already-set")
    export_provider_keys((str(env), str(tmp_path / "missing.env")))
    assert os.environ["GEMINI_API_KEY"] == "from-file"
    assert os.environ["OPENAI_API_KEY"] == "already-set"  # a real env var is never overridden
    assert os.environ["OPENAI_API_BASE"] == "http://example.test"
    assert "APORIA_MODEL_FAST" not in os.environ  # non-key settings stay in Settings only
    assert "EMPTY_API_KEY" not in os.environ
    export_provider_keys(None)  # no env files configured: a no-op
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.delenv("OPENAI_API_BASE")
