"""Probe Telegram Jump to Date click event paths through the existing CDP tab."""
from __future__ import annotations

from fetch_rtss_cdp import RTSS_FRAGMENT, _close_scoped, _ensure_channel, _jump_control
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    pages = [p for c in browser.contexts for p in c.pages]
    page = next(p for p in pages if "web.telegram.org" in p.url)
    _ensure_channel(page)
    page.set_default_timeout(2000)
    control_selector = (
        '#RightColumn [title="Jump to Date"], .RightColumn [title="Jump to Date"], '
        '#MiddleColumn [title="Jump to Date"]'
    )
    control = page.locator(control_selector).filter(visible=True)
    if not control.count():
        search = page.locator(
            '#MiddleColumn [title="Search this chat"], '
            '.MiddleColumn [title="Search this chat"], '
            '#MiddleColumn [aria-label="Search this chat"]'
        ).filter(visible=True).first
        search.click(force=True)
        page.wait_for_timeout(800)
        control = page.locator(control_selector).filter(visible=True)
    methods = [
        ("el.click", lambda: control.evaluate("el => el.click()")),
        ("closest_button.click", lambda: control.evaluate("el => (el.closest('button') || el).click()")),
        ("mouse_events", lambda: [control.dispatch_event(x) for x in ("mousedown", "mouseup", "click")]),
        ("force_pointer", lambda: control.click(force=True)),
    ]
    for name, action in methods:
        _ensure_channel(page)
        _close_scoped(page, "#portals [title='Close']", "calendar close")
        _close_scoped(page, "#RightColumn [title='Close']", "search panel close")
        control = page.locator(control_selector).filter(visible=True)
        if not control.count():
            search = page.locator(
                '#MiddleColumn [title="Search this chat"], '
                '.MiddleColumn [title="Search this chat"], '
                '#MiddleColumn [aria-label="Search this chat"]'
            ).filter(visible=True).first
            search.click(force=True)
            page.wait_for_timeout(400)
            control = page.locator(control_selector).filter(visible=True)
        if not control.count():
            print(f"{name}: control_missing")
            continue
        try:
            action()
            opened = page.locator("#portals .day-button").filter(visible=True).count() > 0
        except PlaywrightTimeoutError:
            opened = False
        print(f"{name}: {'OPEN' if opened else 'closed'}")
        _ensure_channel(page)
        _close_scoped(page, "#portals [title='Close']", "calendar close")
        _close_scoped(page, "#RightColumn [title='Close']", "search panel close")
