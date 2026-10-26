"""Clawksis dashboard settings: hidden models drop out of the Models page, the theme list carries
the Pixel theme and defaults like config (midnight), and Resilience sits before Auxiliary."""

import asyncio
import time

import pytest

from clawk_state import SessionDB


def test_models_analytics_skips_hidden_models(monkeypatch, tmp_path):
    from clawk_cli.web_routers import analytics

    db = SessionDB(tmp_path / "state.db")
    for sid, model, provider in (
        ("s1", "kept-model", "openrouter"),
        ("s2", "gone-model", "openrouter"),
        ("s3", "bare-hidden", "nous"),
    ):
        db.create_session(sid, source="cli", model=model)
        with db._lock:
            db._conn.execute(
                "UPDATE sessions SET billing_provider = ?, started_at = ?, input_tokens = 10 WHERE id = ?",
                (provider, time.time(), sid),
            )
            db._conn.commit()
    monkeypatch.setattr(
        analytics, "_open_session_db_for_profile", lambda profile, read_only=True: db
    )
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(
        analytics,
        "_hidden_models",
        lambda profile=None: ["openrouter|gone-model", "bare-hidden"],
    )

    models = {m["model"] for m in analytics._get_models_analytics(days=30)["models"]}

    assert models == {"kept-model"}


def test_theme_list_has_pixel_and_defaults_to_midnight(monkeypatch):
    pytest.importorskip("fastapi")
    from clawk_cli.web_routers import dashboard_ui

    monkeypatch.setattr(dashboard_ui, "load_config", dict)
    monkeypatch.setattr(dashboard_ui, "_discover_user_themes", list)

    result = asyncio.run(dashboard_ui.get_dashboard_themes())

    assert result["active"] == "midnight"
    assert "pixel" in {t["name"] for t in result["themes"]}


def test_resilience_category_precedes_auxiliary():
    from clawk_cli.web_routers.config_env import _CATEGORY_ORDER

    assert _CATEGORY_ORDER.index("resilience") < _CATEGORY_ORDER.index("auxiliary")
