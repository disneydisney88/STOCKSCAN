"""P6b：load_secrets_env 統一憑證載入——解析、setdefault 優先次序、唔洩值。"""
from __future__ import annotations

import os

from stockscan.io_utils import load_secrets_env


def test_load_secrets_env_merges_without_overriding(tmp_path, monkeypatch):
    secrets = tmp_path / "_secrets"
    secrets.mkdir()
    # 包含：註釋、$env:KEY=VALUE PowerShell 格式、引號值
    (secrets / ".env").write_text(
        "# comment line\n"
        "FOO_TEST_KEY=abc123\n"
        "$env:BAR_TEST_KEY='quoted value'\n"
        "EXISTING_TEST_KEY=from_file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING_TEST_KEY", "already_set")
    # io_utils 係 from config import ROOT——module 內已綁定，要 patch io_utils 嗰個名
    monkeypatch.setattr("stockscan.io_utils.ROOT", tmp_path)
    # load_secrets_env 喺 pytest 入面會 skip（防誤觸生產憑證）——呢個 test 就係測佢，要解鎖
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    loaded = load_secrets_env()

    assert any("_secrets" in mark or ".env" in mark for mark in loaded)
    assert os.environ["FOO_TEST_KEY"] == "abc123"
    assert os.environ["BAR_TEST_KEY"] == "quoted value"
    # setdefault：已設環境變數一定贏，檔案值唔會覆蓋
    assert os.environ["EXISTING_TEST_KEY"] == "already_set"

    monkeypatch.delenv("FOO_TEST_KEY")
    monkeypatch.delenv("BAR_TEST_KEY")
    monkeypatch.delenv("EXISTING_TEST_KEY")
