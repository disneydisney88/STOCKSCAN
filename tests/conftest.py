"""測試共用 fixtures。"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _strip_real_secrets(monkeypatch):
    """P6b 起本機可能有統一憑證檔（repo _secrets/.env／~/.stockscan/.env）。

    測試一律剝走真憑證，避免 load_secrets_env() 令測試誤觸生產 Turso／
    Longbridge／CCASS API（test_state_roundtrip 中過伏：load_state 讀咗
    真實 intraday state）。個別要憑證嘅測試請自行 monkeypatch 假值。
    """
    for key in list(os.environ):
        if key.upper().startswith(("TURSO_", "LONGPORT_", "LONGBRIDGE_", "CCASS_")):
            monkeypatch.delenv(key, raising=False)
