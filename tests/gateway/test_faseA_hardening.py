"""A3 (Hermes→Clawksis quick wins): gateway hardening.

Covers the inbound-media size cap (anti-OOM), user-maintained channel aliases,
and hot-``git pull`` code-skew detection.
"""

import pytest

from gateway.platforms import base as gw_base
from gateway import channel_directory as cd
from gateway import code_skew


class TestInboundMediaSizeCap:
    def test_validate_under_limit_ok(self):
        gw_base.validate_inbound_media_size(10, media_type="image", max_bytes=100)

    def test_validate_over_limit_raises(self):
        with pytest.raises(ValueError):
            gw_base.validate_inbound_media_size(101, media_type="image", max_bytes=100)

    def test_validate_zero_disables_cap(self):
        gw_base.validate_inbound_media_size(10 ** 9, media_type="video", max_bytes=0)

    def test_cache_image_rejects_oversized(self, monkeypatch):
        monkeypatch.setattr(gw_base, "get_inbound_media_max_bytes", lambda: 10)
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50  # valid header, but > 10 bytes
        with pytest.raises(ValueError):
            gw_base.cache_image_from_bytes(png, ".png")


class TestChannelAliases:
    def test_rename_existing(self, monkeypatch):
        monkeypatch.setattr(
            cd, "_load_channel_aliases", lambda: {"whatsapp": {"123@g.us": "Ventas"}}
        )
        plats = {"whatsapp": [{"id": "123@g.us", "name": "Grupo", "type": "group"}]}
        cd._apply_channel_aliases(plats)
        assert plats["whatsapp"][0]["name"] == "Ventas"

    def test_inject_placeholder_for_unknown(self, monkeypatch):
        monkeypatch.setattr(
            cd, "_load_channel_aliases", lambda: {"whatsapp": {"999@g.us": "Soporte"}}
        )
        plats = {}
        cd._apply_channel_aliases(plats)
        assert any(
            e["id"] == "999@g.us" and e["name"] == "Soporte"
            for e in plats["whatsapp"]
        )

    def test_blank_alias_ignored(self, monkeypatch):
        monkeypatch.setattr(
            cd, "_load_channel_aliases", lambda: {"whatsapp": {"1@g.us": "  "}}
        )
        plats = {"whatsapp": [{"id": "1@g.us", "name": "Keep", "type": "group"}]}
        cd._apply_channel_aliases(plats)
        assert plats["whatsapp"][0]["name"] == "Keep"


class TestCodeSkew:
    def test_no_boot_fingerprint_no_skew(self, monkeypatch):
        monkeypatch.setattr(code_skew, "_boot_fingerprint", None)
        assert code_skew.detect_code_skew() is None

    def test_same_fingerprint_no_skew(self, monkeypatch):
        monkeypatch.setattr(code_skew, "_boot_fingerprint", "git:main:abc123")
        monkeypatch.setattr(code_skew, "_fingerprint", lambda: "git:main:abc123")
        assert code_skew.detect_code_skew() is None

    def test_drift_detected(self, monkeypatch):
        monkeypatch.setattr(code_skew, "_boot_fingerprint", "git:main:aaaaaaaaaaaa")
        monkeypatch.setattr(code_skew, "_fingerprint", lambda: "git:main:bbbbbbbbbbbb")
        result = code_skew.detect_code_skew()
        assert result is not None
        boot, disk = result
        assert boot.startswith("aaaaaaaaaa")
        assert disk.startswith("bbbbbbbbbb")
