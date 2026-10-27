"""Router models on OpenRouter (``typesafe/jev-router``, ``openrouter/auto``...) publish ``-1`` as
their rate: the price depends on the model each request is routed to. Such a row carries no
price at all — never a negative one the picker would show as "$-1000000" — while ordinary rows
keep theirs; and TypeSafe's Jev Router is offered in the OpenRouter picker."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

import clawk_cli.models as models_mod
from clawk_cli import models_pricing
from clawk_cli.models import OPENROUTER_MODELS, _PROVIDER_MODELS


@pytest.fixture(autouse=True)
def _clear_pricing_cache():
    models_pricing._pricing_cache.clear()
    models_pricing._pricing_cache_retry_after.clear()
    yield
    models_pricing._pricing_cache.clear()
    models_pricing._pricing_cache_retry_after.clear()


def test_a_router_row_has_no_price_and_a_normal_row_keeps_its_own(monkeypatch):
    payload = {
        "data": [
            {
                "id": "typesafe/jev-router",
                "pricing": {"prompt": "-1", "completion": "-1"},
            },
            {
                "id": "z-ai/glm-5.3-flash",
                "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
            },
        ]
    }

    def _fake_urlopen(req, timeout=8.0):
        resp = MagicMock()
        resp.read.return_value = json.dumps(payload).encode()
        resp.__enter__ = lambda self: self
        resp.__exit__ = lambda *a: False
        return resp

    monkeypatch.setattr(models_mod, "_urlopen_model_catalog_request", _fake_urlopen)
    prices = models_pricing.fetch_models_with_pricing(
        base_url="https://openrouter.example/api"
    )

    assert "typesafe/jev-router" not in prices
    assert prices["z-ai/glm-5.3-flash"]["prompt"] == "0.0000001"


def test_jev_router_is_in_the_openrouter_picker_only():
    described = dict(OPENROUTER_MODELS)
    assert "typesafe/jev-router" in described
    assert "Jev" in described["typesafe/jev-router"]
    assert "typesafe/jev-router" not in _PROVIDER_MODELS["nous"]
