"""Behaviour contracts for the Kronos dashboard snapshot (``kronos_dashboard.py``).

The snapshot at ``$CLAWK_HOME/dashboards/kronos.json`` is read by the web dashboard, so every
snapshot is validated against the contract (version 1: stats/table/list/chart/text panels and
their caps), in English and Spanish, empty and full. Writes are atomic and stay under 512 KiB;
an unreadable config still renders; ``refresh_safely`` never raises. Also pins the SKILL.md
frontmatter budget the skill catalog parses (first 4000 chars) and the dashboard declaration.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from agent.skill_utils import extract_skill_config_vars, parse_frontmatter

REPO = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO / "skills" / "finance" / "kronos"
SCRIPTS = SKILL_DIR / "scripts"


def _load(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # siblings import each other by these names
    spec.loader.exec_module(module)
    return module


kc = _load("_kronos_common")
trade = _load("etoro_trade")
lessons = _load("_kronos_lessons")
dash = _load("kronos_dashboard")

NOW = datetime(2026, 10, 26, 14, 3, tzinfo=kc.UTC)
TONES = {"positive", "negative", "warning", "neutral"}
FORMATS = {"text", "number", "money", "percent", "datetime"}
EXPECTED_PANELS = [
    "summary",
    "goals",
    "lessons",
    "bought",
    "sold",
    "refused",
    "accuracy_chart",
    "accuracy_by_symbol",
    "backtests",
    "strategy",
    "forecasts",
    "disclaimer",
]


# ── Contract validator (mirrors the documented snapshot contract) ──


def _iso_utc(value) -> None:
    assert isinstance(value, str) and value.endswith("Z"), value
    datetime.fromisoformat(value[:-1])


def _tone(value) -> None:
    assert value is None or value in TONES, value


def _stats(panel) -> None:
    assert 0 < len(panel["items"]) <= 12
    for item in panel["items"]:
        assert isinstance(item["label"], str)
        assert isinstance(item["value"], (str, int, float)) and not isinstance(
            item["value"], bool
        )
        assert isinstance(item.get("hint", ""), str)
        _tone(item.get("tone"))


def _cell(value, fmt: str) -> None:
    if value is None:
        return
    if fmt in {"number", "money", "percent"}:
        assert isinstance(value, (int, float)) and not isinstance(value, bool), value
    elif fmt == "datetime":
        _iso_utc(value)
    else:
        assert isinstance(value, (str, int, float)), value


def _table(panel) -> None:
    columns = panel["columns"]
    assert columns and len({c["key"] for c in columns}) == len(columns)
    for column in columns:
        assert isinstance(column["label"], str)
        assert column.get("align", "left") in {"left", "right"}
        assert column.get("format", "text") in FORMATS
    assert len(panel["rows"]) <= 200
    for row in panel["rows"]:
        _tone(row.get("_tone"))
        assert set(row) - {"_tone"} <= {c["key"] for c in columns}
        for column in columns:
            _cell(row.get(column["key"]), column.get("format", "text"))
    assert isinstance(panel.get("empty", ""), str)


def _list(panel) -> None:
    assert len(panel["items"]) <= 100
    for item in panel["items"]:
        assert isinstance(item["title"], str) and item["title"]
        assert isinstance(item.get("body", ""), str)
        assert isinstance(item.get("meta", ""), str)
        _tone(item.get("tone"))


def _chart(panel) -> None:
    assert panel["kind"] in {"line", "bar"}
    assert 0 < len(panel["series"]) <= 4
    for series in panel["series"]:
        assert isinstance(series["name"], str)
        assert len(series["points"]) <= 500
        for x, y in series["points"]:
            assert isinstance(x, (str, int, float))
            if isinstance(x, str):
                _iso_utc(x)
            assert isinstance(y, (int, float)) and not isinstance(y, bool)


def _text(panel) -> None:
    assert isinstance(panel["body"], str) and panel["body"]


VALIDATORS = {
    "stats": _stats,
    "table": _table,
    "list": _list,
    "chart": _chart,
    "text": _text,
}


def validate(snapshot: dict) -> None:
    assert snapshot["version"] == 1
    _iso_utc(snapshot["updated_at"])
    for key in ("title", "subtitle"):
        assert isinstance(snapshot.get(key, ""), str)
    panels = snapshot["panels"]
    assert 0 < len(panels) <= 24
    for panel in panels:
        assert isinstance(panel["title"], str) and panel["title"]
        assert isinstance(panel.get("id", ""), str)
        assert isinstance(panel.get("description", ""), str)
        assert panel.get("width", "full") in {"full", "half"}
        VALIDATORS[panel["type"]](panel)


def _panel(snapshot: dict, panel_id: str) -> dict:
    return next(p for p in snapshot["panels"] if p.get("id") == panel_id)


# ── Fixtures ──


def _write_config(home: Path, text: str) -> Path:
    path = home / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _append(path: Path, rows) -> None:
    for row in rows:
        kc.append_jsonl(path, row)


def _full_home(home: Path) -> Path:
    """A profile with goals, buys, closes, a refusal, scored and pending forecasts, lessons."""
    kdir = home / "kronos"
    ts = NOW.isoformat()
    _append(
        kdir / "trades.jsonl",
        [
            {
                "id": "a",
                "ts": ts,
                "action": "open",
                "account": "demo",
                "symbol": "AAPL",
                "instrument_id": 1001,
                "amount": 50.0,
                "status": "filled",
                "reason": "adds_value",
            },
            {
                "id": "b",
                "ts": ts,
                "action": "open",
                "account": "demo",
                "symbol": "TSLA",
                "instrument_id": 7,
                "amount": 30.0,
                "status": "unknown",
                "reason": "user asked",
                "user_requested": True,
            },
            {
                "id": "c",
                "ts": ts,
                "action": "close",
                "account": "demo",
                "instrument_id": 1001,
                "units": "all",
                "pnl_usd": -4.5,
                "reason": "stop hit",
                "status": "submitted",
            },
        ],
    )
    _append(
        kdir / "refused.jsonl",
        [
            {
                "id": "r",
                "ts": ts,
                "symbol": "AAPL",
                "amount": 50,
                "kind": "lesson",
                "refusal": "Kronos got the direction of AAPL right in only 1 of its last 6",
            }
        ],
    )
    forecasts = []
    for index in range(12):
        day = (NOW - timedelta(days=40 - 3 * index)).replace(tzinfo=None)
        record = {
            "id": f"f{index}",
            "made_at": kc.iso_z(day),
            "symbol": "AAPL" if index % 2 else "BTC",
            "interval": "1 day",
            "step_seconds": 86400,
            "horizon": 5,
            "last_timestamp": day.isoformat(),
            "last_close": 100.0,
            "target_timestamp": (day + timedelta(days=5)).isoformat(),
            "predicted_close": 102.0,
            "direction": "up",
            "band": [101.0, 103.0],
        }
        if index < 10:
            record["outcome"] = {
                "actual_close": 101.5 if index % 3 else 98.0,
                "actual_timestamp": (day + timedelta(days=5)).isoformat(),
                "actual_direction": "up" if index % 3 else "down",
                "direction_hit": bool(index % 3),
                "error_pct": 1.2,
                "beat_naive": bool(index % 3),
                "in_band": bool(index % 3),
            }
        forecasts.append(record)
    _append(kdir / "forecasts.jsonl", forecasts)
    current = lessons.build_lessons(
        kc.fold_rows(forecasts), kc.fold_rows(kc.read_jsonl(kdir / "trades.jsonl"))
    )
    current["low_accuracy|AAPL|1 day"] = lessons._lesson(
        "low_accuracy", "negative", "AAPL", "1 day", {"hits": 1, "n": 6}
    )
    lessons.update_lessons(current, NOW, kdir / "lessons.jsonl")
    return kdir


def _refresh(home: Path, config: Path) -> dict:
    out = dash.refresh(
        config_path=config,
        kronos_dir=home / "kronos",
        out=home / "d" / "kronos.json",
        now=NOW,
    )
    return json.loads(out.read_text(encoding="utf-8"))


# ── Tests ──


def test_an_empty_profile_still_renders_a_valid_snapshot(tmp_path):
    snapshot = _refresh(tmp_path, tmp_path / "missing.yaml")
    validate(snapshot)
    assert [p["id"] for p in snapshot["panels"]] == EXPECTED_PANELS
    assert snapshot["updated_at"] == "2026-10-26T14:03:00Z"
    assert snapshot["subtitle"] == "eToro demo · max $100/order · trading off"
    assert _panel(snapshot, "summary")["title"] == "Overview"
    assert "Not set yet" in _panel(snapshot, "goals")["description"]
    assert (
        _panel(snapshot, "bought")["rows"] == [] and _panel(snapshot, "bought")["empty"]
    )


def test_a_full_profile_renders_what_was_bought_sold_refused_and_learned_in_spanish(
    tmp_path,
):
    config = _write_config(
        tmp_path,
        "display:\n  language: es-ES\nskills:\n  config:\n    kronos:\n      trading:\n"
        "        enabled: true\n      goals:\n        watchlist: [aapl, BTC]\n        risk: alto\n",
    )
    _full_home(tmp_path)
    snapshot = _refresh(tmp_path, config)
    validate(snapshot)
    assert snapshot["subtitle"] == "eToro demo · máx. $100/orden"
    assert _panel(snapshot, "lessons")["title"] == "Lo que aprendió"
    goals = {i["label"]: i["value"] for i in _panel(snapshot, "goals")["items"]}
    assert goals["Lista de seguimiento"] == "AAPL, BTC" and goals["Riesgo"] == "alto"

    bought = _panel(snapshot, "bought")["rows"]
    assert [(r["symbol"], r["status"], r["who"], r["_tone"]) for r in bought] == [
        ("TSLA", "desconocido", "Tú", "warning"),
        ("AAPL", "ejecutada", "Kronos", "positive"),
    ]
    (sold,) = _panel(snapshot, "sold")["rows"]
    assert (sold["symbol"], sold["pnl"], sold["units"], sold["_tone"]) == (
        "AAPL",
        -4.5,
        "todas",
        "negative",
    )
    (refused,) = _panel(snapshot, "refused")["rows"]
    assert refused["kind"] == "lecciones" and "only 1 of its last 6" in refused["why"]

    items = _panel(snapshot, "lessons")["items"]
    low = next(i for i in items if "Baja precisión" in i["title"])
    assert low["tone"] == "negative" and "acertó la dirección solo 1/6" in low["body"]
    results = {r["result"] for r in _panel(snapshot, "forecasts")["rows"]}
    assert results == {"acierto", "fallo", "pendiente"}
    series = _panel(snapshot, "accuracy_chart")["series"]
    assert series[0]["points"] and {s["name"] for s in series} >= {"AAPL", "BTC"}
    summary = {i["label"]: i for i in _panel(snapshot, "summary")["items"]}
    assert summary["Compras hoy"]["value"] == "2 / 5"
    assert summary["Órdenes en curso"]["tone"] == "warning"
    assert summary["P&L cerrado (est.)"]["value"] == "-$4.50"


def test_an_unreadable_config_still_renders_with_a_warning(tmp_path):
    config = _write_config(tmp_path, "skills: [unclosed\n")
    snapshot = _refresh(tmp_path, config)
    validate(snapshot)
    assert "subtitle" not in snapshot
    (first, *_rest) = _panel(snapshot, "summary")["items"]
    assert first["tone"] == "warning" and first["value"] == "?"


def test_oversized_snapshots_are_trimmed_under_512_kib():
    rows = [{"time": "2026-10-26T14:03:00Z", "reason": "x" * 3000} for _ in range(200)]
    snapshot = {
        "version": 1,
        "updated_at": "2026-10-26T14:03:00Z",
        "panels": [
            {
                "id": "t",
                "type": "table",
                "title": "T",
                "columns": [
                    {"key": "time", "label": "Time", "format": "datetime"},
                    {"key": "reason", "label": "Reason"},
                ],
                "rows": rows,
            },
            {
                "id": "c",
                "type": "chart",
                "title": "C",
                "kind": "line",
                "series": [
                    {"name": "s", "points": [["2026-10-26T14:03:00Z", 1.0]] * 500}
                ],
            },
        ],
    }
    data = dash.encode(snapshot)
    assert len(data) <= dash.MAX_BYTES
    decoded = json.loads(data)
    validate(decoded)
    assert 0 < len(decoded["panels"][0]["rows"]) < 200


def test_writes_are_atomic(tmp_path, monkeypatch):
    out = tmp_path / "dashboards" / "kronos.json"
    out.parent.mkdir()
    out.write_text('{"version": 1, "old": true}', encoding="utf-8")
    snapshot = {
        "version": 1,
        "updated_at": "2026-10-26T14:03:00Z",
        "panels": [{"type": "text", "title": "T", "body": "b"}],
    }

    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(dash.os, "replace", failing_replace)
    with pytest.raises(OSError):
        dash.write_snapshot(snapshot, out)
    assert json.loads(out.read_text(encoding="utf-8"))["old"] is True
    assert os.listdir(out.parent) == ["kronos.json"]  # no temp file left behind

    monkeypatch.undo()
    dash.write_snapshot(snapshot, out)
    assert json.loads(out.read_text(encoding="utf-8")) == snapshot
    assert os.listdir(out.parent) == ["kronos.json"]


def test_refresh_safely_never_raises(monkeypatch, capsys):
    def broken(**_kwargs):
        raise KeyError("panel bug")

    monkeypatch.setattr(dash, "refresh", broken)
    assert dash.refresh_safely() is None
    assert "not refreshed" in capsys.readouterr().err


def test_the_cli_writes_into_the_profile_home(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAWK_HOME", str(tmp_path))
    assert dash.main([]) == 0
    path = Path(json.loads(capsys.readouterr().out)["path"])
    assert path == tmp_path / "dashboards" / "kronos.json"
    validate(json.loads(path.read_text(encoding="utf-8")))


def test_skill_frontmatter_declares_the_dashboard_within_the_catalog_budget():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    end = text.index("\n---", 3) + len("\n---")
    assert end < 3500, f"frontmatter is {end} chars; the catalog parses only 4000"
    frontmatter, _body = parse_frontmatter(text[:4000])  # what tools/skills_tool reads
    clawk = frontmatter["metadata"]["clawk"]
    assert clawk["dashboard"]["title"] == "Kronos"
    assert clawk["dashboard"]["description"].strip()
    keys = {var["key"] for var in extract_skill_config_vars(frontmatter)}
    assert {
        f"kronos.goals.{k}"
        for k in ("watchlist", "objective", "risk", "horizon", "schedule")
    } <= keys
    assert "kronos.trading.max_order_usd" in keys
