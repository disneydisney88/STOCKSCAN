from __future__ import annotations

import importlib.util
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def _module():
    path = Path(__file__).parents[1] / "scripts" / "fetch_rtss_cdp.py"
    spec = importlib.util.spec_from_file_location("fetch_rtss_cdp", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Locator:
    def __init__(self):
        self.evaluated = []

    def wait_for(self, **kwargs):
        return None

    def scroll_into_view_if_needed(self, **kwargs):
        return None

    def click(self, **kwargs):
        raise PlaywrightTimeoutError("covered")

    def evaluate(self, expression):
        self.evaluated.append(expression)


class _Page:
    url = "https://web.telegram.org/a/#-1002795969450"


def test_safe_click_falls_back_to_js_after_pointer_timeout(capsys):
    module = _module()
    locator = _Locator()
    module._safe_click(_Page(), locator, "test control")
    assert locator.evaluated == ["el => el.click()"]
    assert "[rtss-cdp] click test control" in capsys.readouterr().out
