"""Regression tests: `clawk setup` must always end up asking for a model.

After the Nous "Quick Setup" prompt was removed, the first-time/full setup
delegates to select_provider_and_model(), which leads with a *provider*
picker and only asks for the model inside the chosen provider's flow. That
made the model question skippable (picker left "unchanged", a provider's
auth sub-menu cancelled, an error swallowed, or `--quick` never calling it).

These tests pin the guarantee that:
  * setup_model_provider() re-runs the model flow until a model is set,
    capped so it never hangs; and
  * `clawk setup --quick` runs the model flow when model.default is empty,
    and skips it when a model is already configured.
"""

from __future__ import annotations

from clawk_cli.config import load_config, save_config
from clawk_cli.setup import setup_model_provider, _run_quick_setup


def _clear_provider_env(monkeypatch):
    for key in (
        "CLAWK_INFERENCE_PROVIDER",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_TOKEN",
        "GLM_API_KEY",
        "KIMI_API_KEY",
        "MINIMAX_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def _model_default(cfg=None) -> str:
    """Read model.default the same way production does (str or dict shaped)."""
    cfg = cfg if cfg is not None else load_config()
    m = cfg.get("model")
    if isinstance(m, dict):
        return str(m.get("default") or "").strip()
    return str(m or "").strip()


def _write_model(model_name, provider="anthropic"):
    """Simulate what a _model_flow_* function persists to disk."""
    cfg = load_config()
    m = cfg.get("model")
    if not isinstance(m, dict):
        m = {"default": m} if m else {}
        cfg["model"] = m
    m["provider"] = provider
    m["default"] = model_name
    save_config(cfg)


def _silence_quick_setup_prompts(monkeypatch):
    monkeypatch.setattr("clawk_cli.setup.prompt_checklist", lambda *a, **k: [])
    monkeypatch.setattr("clawk_cli.setup.prompt_yes_no", lambda *a, **k: False)
    monkeypatch.setattr("clawk_cli.setup.prompt", lambda *a, **k: "")


def test_model_step_insists_until_a_model_is_chosen(tmp_path, monkeypatch):
    """If the first provider/model pass leaves no model, the step re-runs."""
    monkeypatch.setenv("CLAWK_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)

    calls = {"n": 0}

    def fake_select():
        # First pass: user "leaves unchanged" -> nothing persisted.
        # Second pass: user actually picks a model.
        calls["n"] += 1
        if calls["n"] >= 2:
            _write_model("claude-opus-4-8")

    monkeypatch.setattr("clawk_cli.main.select_provider_and_model", fake_select)

    config = load_config()
    assert not _model_default(config)  # seeded empty

    setup_model_provider(config)

    assert calls["n"] == 2  # initial pass + exactly one insist retry
    assert _model_default() == "claude-opus-4-8"
    # config dict is re-synced from disk in place for downstream wizard steps
    assert _model_default(config) == "claude-opus-4-8"


def test_model_step_does_not_retry_when_model_set_first_try(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAWK_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)

    calls = {"n": 0}

    def fake_select():
        calls["n"] += 1
        _write_model("claude-sonnet-4-6")

    monkeypatch.setattr("clawk_cli.main.select_provider_and_model", fake_select)

    config = load_config()
    setup_model_provider(config)

    assert calls["n"] == 1  # set on first try -> no insist loop
    assert _model_default() == "claude-sonnet-4-6"


def test_model_step_retry_is_capped_and_never_hangs(tmp_path, monkeypatch):
    """A user who keeps cancelling must not loop forever."""
    monkeypatch.setenv("CLAWK_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)

    calls = {"n": 0}

    def fake_select():
        calls["n"] += 1  # never persists a model

    monkeypatch.setattr("clawk_cli.main.select_provider_and_model", fake_select)

    config = load_config()
    setup_model_provider(config)  # must return, not hang

    # 1 initial pass + at most 2 insist retries
    assert calls["n"] == 3
    assert not _model_default()


def test_quick_setup_runs_model_flow_when_model_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAWK_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)
    _silence_quick_setup_prompts(monkeypatch)

    called = {"n": 0}

    def spy_model_provider(config, *, quick=False):
        called["n"] += 1
        _write_model("claude-opus-4-8")
        config.clear()
        config.update(load_config())

    monkeypatch.setattr("clawk_cli.setup.setup_model_provider", spy_model_provider)

    config = load_config()
    assert not _model_default(config)  # seeded empty

    _run_quick_setup(config, tmp_path)

    assert called["n"] == 1  # quick setup asked for the model
    assert _model_default() == "claude-opus-4-8"


def test_quick_setup_skips_model_flow_when_already_set(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAWK_HOME", str(tmp_path))
    _clear_provider_env(monkeypatch)
    _silence_quick_setup_prompts(monkeypatch)

    _write_model("claude-sonnet-4-6")  # model already configured

    called = {"n": 0}

    def spy_model_provider(config, *, quick=False):
        called["n"] += 1

    monkeypatch.setattr("clawk_cli.setup.setup_model_provider", spy_model_provider)

    config = load_config()
    _run_quick_setup(config, tmp_path)

    assert called["n"] == 0  # configured model is not re-prompted in --quick
