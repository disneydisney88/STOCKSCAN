#!/usr/bin/env python
"""只讀現有 Chrome Telegram Web DOM，擷取 RTSS 純文字訊息。

唔會 click、focus、截圖、讀 media 或呼叫 Telegram API；raw staging 留在
``data/rtss/``（gitignored），T2/T3 再由 parser 轉成 alert CSV。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stockscan.io_utils import now_hkt, today_hkt
from stockscan.rtss_parser import clean_alert_text

CDP_URL = "http://127.0.0.1:9222"
# Telegram Web uses the -100 prefix for channel peer IDs; older exports omit it.
# Match the stable numeric channel ID in either URL form.
RTSS_FRAGMENT = "2795969450"
OUT_DIR = Path("data/rtss")
CHECKPOINT_PATH = OUT_DIR / "backfill_ckpt.json"
MAX_SCROLL_ROUNDS = 1800
STABLE_ROUNDS_LIMIT = 20
SCROLL_OVERLAP_RATIO = 0.6
TITLE_DATE_RE = re.compile(r"^(\d{1,2} [A-Za-z]+ \d{4}),")
TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}:\d{2})\b")


def _date_from_title(title: str) -> date | None:
    match = TITLE_DATE_RE.search(title or "")
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d %B %Y").date()
    except ValueError:
        return None


def _date_from_label(label: str) -> date | None:
    label = " ".join(str(label or "").split())
    if label.lower() == "today":
        return today_hkt()
    if label.lower() == "yesterday":
        return today_hkt() - timedelta(days=1)
    weekdays = {datetime(2000, 1, 3).strftime("%A").lower(): 0}
    weekdays.update({(datetime(2000, 1, 3) + timedelta(days=i)).strftime("%A").lower(): i
                     for i in range(7)})
    if label.lower() in weekdays:
        today = today_hkt()
        for delta in range(7):
            candidate = today - timedelta(days=delta)
            if candidate.strftime("%A").lower() == label.lower():
                return candidate
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%B %d", "%b %d"):
        try:
            if fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
                return datetime.strptime(label, fmt).date()
            return datetime.strptime(f"{today_hkt().year} {label}", f"%Y {fmt}").date()
        except ValueError:
            continue
    return None


def _visible_date_labels(page) -> list[str]:
    """Return visible Telegram message date separators only."""
    return page.locator(".message-date-group .sticky-date").evaluate_all("""els => els
      .filter(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length))
      .map(el => (el.innerText || el.textContent || '').trim())
      .filter(Boolean)""")


def _message_rows(page) -> list[dict]:
    """Read message text/title only; no DOM action which changes Telegram state."""
    return page.locator(".message, .Message").evaluate_all(
        """els => els.map((el, index) => {
          const textEl = el.querySelector('.translatable-message, .text-content');
          if (!textEl) return null;
          const timeEl = el.querySelector('.time-inner, .time, .message-time');
          const dateEl = el.closest('.message-date-group')?.querySelector('.sticky-date');
          return {
            ordinal: index,
            raw_text: (textEl || el).innerText || (textEl || el).textContent || '',
            dom_title: timeEl ? (timeEl.getAttribute('title') || '') : '',
            date_label: dateEl ? (dateEl.innerText || dateEl.textContent || '') : '',
            dom_message_id: el.getAttribute('data-message-id') || ''
          };
        }).filter(Boolean)"""
    )


def _assert_client(page) -> str:
    """Fail loudly if the open tab is not a supported Telegram Web client."""
    path = urlparse(page.url).path.rstrip("/")
    if path.endswith("/a"):
        client = "a"
        if not page.locator(".MessageList.custom-scroll").count():
            raise RuntimeError("Telegram Web A client asserted, but .MessageList is missing")
    elif path.endswith("/k"):
        client = "k"
        if not page.locator(".bubbles, .bubbles-scrollable").count():
            raise RuntimeError("Telegram Web K client asserted, but .bubbles container is missing")
    else:
        raise RuntimeError(f"Unsupported Telegram Web client path: {path or '/'} (expected /a or /k)")
    container = _scrollable(page)
    metrics = container.evaluate("el => ({scrollHeight: el.scrollHeight, clientHeight: el.clientHeight})")
    if metrics["scrollHeight"] <= metrics["clientHeight"]:
        raise RuntimeError(
            f"Telegram {client} message container is not scrollable: "
            f"scrollHeight={metrics['scrollHeight']} clientHeight={metrics['clientHeight']}"
        )
    print(f"[rtss-cdp] scroll_container=verified scrollHeight={metrics['scrollHeight']} clientHeight={metrics['clientHeight']}")
    print(f"[rtss-cdp] client={client} asserted")
    return client


def _scroll_up(scroll, page) -> None:
    """The one scroll primitive shared by history probe and backfill."""
    page.bring_to_front()
    box = scroll.bounding_box()
    if not box:
        raise RuntimeError("RTSS message scroll container has no bounding box")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    client_height = scroll.evaluate("el => el.clientHeight")
    step = max(1, int(client_height * SCROLL_OVERLAP_RATIO))
    page.mouse.wheel(0, -step)
    page.wait_for_timeout(400)


def _message_ids(page) -> set[str]:
    rows = _message_rows(page)
    return {
        str(row.get("dom_message_id") or hashlib.sha256(
            f"{row.get('dom_title', '')}\n{row.get('raw_text', '')}".encode("utf-8", errors="replace")
        ).hexdigest())
        for row in rows
    }


def _probe_history_ready(page, max_iter: int = 200, timeout_s: int = 20) -> bool:
    """Scroll to the sentinel before deciding that history is unavailable."""
    page.bring_to_front()
    scroll = _scrollable(page)
    if not scroll.count():
        raise RuntimeError("history not loading: message scroll container not found")
    before = _message_ids(page)
    if not before:
        raise RuntimeError("no messages in DOM — wrong tab or channel not opened")
    header_has_updating = bool(page.get_by_text(re.compile(r"^updating\.?\.?$", re.I)).count())
    if header_has_updating:
        print("[rtss-cdp] header shows updating; using functional history probe")
    loaded = False
    for i in range(max_iter):
        scroll_top = scroll.evaluate("el => el.scrollTop")
        print(f"[rtss-cdp] probe iter={i} scrollTop={scroll_top}")
        if scroll_top <= 200:
            break
        _scroll_up(scroll, page)
        after = _message_ids(page)
        if after - before:
            loaded = True
            before = after
            print(f"[rtss-cdp] history_probe=new_nodes_at_iter={i}")
    page.wait_for_timeout(timeout_s * 1000 // 4)
    after = _message_ids(page)
    if after - before:
        loaded = True
    if scroll.evaluate("el => el.scrollTop <= 200") and loaded:
        print("[rtss-cdp] history_probe=ready_at_sentinel")
        return True
    if scroll.evaluate("el => el.scrollTop <= 200"):
        print("[rtss-cdp] history_probe=at_top_no_new_messages")
        return True
    if loaded:
        print("[rtss-cdp] history_probe=ready_loaded_virtualized_batches")
        return True
    raise RuntimeError("history not loading: no new messages after probe scroll")


def _scroll_to_latest(page, target: date, max_iter: int = 300) -> None:
    """Restore the latest side after the sentinel probe's destructive scroll.

    Telegram Web virtualizes the message list: assigning scrollHeight once only
    advances one loaded batch.  Keep asking for the next batch until the DOM
    contains the requested end date, otherwise the following harvest would
    start in an old historical window.
    """
    scroll = _scrollable(page)
    if not scroll.count():
        raise RuntimeError("RTSS message scroll container not found")
    last_max: date | None = None
    no_progress = 0
    for i in range(max_iter):
        rows = _message_rows(page)
        dates = [
            _date_from_title(str(row.get("dom_title") or ""))
            or _date_from_label(str(row.get("date_label") or ""))
            for row in rows
        ]
        dates = [d for d in dates if d]
        max_seen = max(dates) if dates else None
        if i == 0 or i % 10 == 0 or max_seen != last_max:
            print(f"[rtss-cdp] restore_latest iter={i} max_date={max_seen or '—'}")
        if max_seen and max_seen >= target:
            print(f"[rtss-cdp] restore_latest=ready max_date={max_seen}")
            return
        if max_seen == last_max:
            no_progress += 1
        else:
            no_progress = 0
            last_max = max_seen
        if no_progress >= 12:
            raise RuntimeError(
                f"latest restore stalled before {target.isoformat()} "
                f"(last max date {max_seen or '—'})"
            )
        scroll.evaluate("el => { el.scrollTop = el.scrollHeight; }")
        page.wait_for_timeout(800)
    raise RuntimeError(f"latest restore exceeded {max_iter} batches before {target.isoformat()}")


def _ensure_jump_control(page) -> None:
    """Open Telegram Web A's search panel before locating its calendar control."""
    ctl = page.locator('[title="Jump to Date"]')
    if ctl.count() and ctl.first.is_visible():
        return
    for selector in ('[title="Search this chat"]', '[title="Search"]',
                     '[aria-label="Search"]', 'button .icon-search'):
        button = page.locator(selector).first
        if button.count() and button.is_visible():
            button.click()
            page.wait_for_timeout(500)
            break
    ctl = page.locator('[title="Jump to Date"]')
    if not (ctl.count() and ctl.first.is_visible()):
        candidates = page.evaluate("""() => [...document.querySelectorAll(
          'button,[role="button"],[title],[aria-label]')]
          .map(e => ({cls:String(e.className), title:e.getAttribute('title'),
                      aria:e.getAttribute('aria-label')}))
          .filter(o => o.title || o.aria)""")
        raise RuntimeError(
            f"Jump to Date control not found after opening search; candidates={candidates}"
        )


def _jump_to_date(page, target: date) -> None:
    """Use Telegram Web A's own calendar, then leave the list at target."""
    # Telegram Web A currently rolls a clicked month-end 31 over to the next
    # month's day 1 (confirmed in the live DOM for 2026-03-31/07-31).  Landing
    # on the following day 1 loads the adjacent day 31 into the virtualized window; the
    # caller's verify_anchor(target) still requires the real target separator.
    picker_target = target + timedelta(days=1) if target.day == 31 else target
    if picker_target != target:
        print(
            f"[rtss-cdp] calendar_day31_workaround target={target.isoformat()} "
            f"picker_target={picker_target.isoformat()}"
        )
    before_labels = _visible_date_labels(page)
    # A prior interrupted/manual probe may leave the calendar modal open.
    # Close that stale backdrop before opening a fresh picker.
    stale_close = page.locator("#portals [title='Close'], .modal-backdrop").first
    if stale_close.count() and stale_close.is_visible():
        try:
            if "modal-backdrop" in (stale_close.get_attribute("class") or ""):
                stale_close.click(position={"x": 5, "y": 5})
            else:
                stale_close.click()
            page.wait_for_timeout(200)
        except PlaywrightTimeoutError:
            pass
    _ensure_jump_control(page)
    ctl = page.locator('[title="Jump to Date"]').first
    ctl.wait_for(state="visible", timeout=3000)
    ctl.click()
    page.wait_for_timeout(300)
    month_name = picker_target.strftime("%B %Y")
    for _ in range(24):
        portal = page.locator("#portals")
        lines = [line.strip() for line in portal.inner_text().splitlines() if line.strip()]
        current_month_name = lines[0] if lines else ""
        if current_month_name == month_name:
            break
        try:
            current_month = datetime.strptime(current_month_name, "%B %Y").date()
        except ValueError as exc:
            raise RuntimeError(
                f"Telegram date picker month heading is unreadable: {current_month_name!r}"
            ) from exc
        direction = "previous" if current_month > picker_target else "next"
        arrow = portal.locator(
            f"button:has(.icon-{direction}), "
            f"button:has(.icon-{'left' if direction == 'previous' else 'right'})"
        ).first
        if not arrow.count() or arrow.is_disabled():
            print(
                f"[rtss-cdp] calendar_boundary target_month={month_name} "
                f"direction={direction} control=missing_or_disabled"
            )
            return
        arrow.click()
        page.wait_for_timeout(100)
    else:
        raise RuntimeError(f"Telegram date picker could not reach {month_name}")
    # Keep one live locator narrowed by exact text; Telegram re-renders the
    # calendar while Playwright inspects it, so saved nth() locators are unsafe.
    day_buttons = portal.locator("button.day-button").filter(
        has_text=re.compile(rf"^{picker_target.day}$")
    )
    target_button = day_buttons.first
    if not target_button.count() or target_button.is_disabled():
        raise RuntimeError(
            f"Telegram date picker has no enabled day {picker_target.day} for {month_name}"
        )
    target_button.click()
    page.wait_for_timeout(300)
    selected_days = portal.locator("button.day-button.selected").all_inner_texts()
    print(
        f"[rtss-cdp] calendar_selection target={target.isoformat()} "
        f"month={month_name} selected={selected_days} before={before_labels}"
    )
    confirm = portal.locator("button.Button.default.primary").filter(
        has_text=re.compile(r"^Jump to Date$")
    )
    visible_confirms = [
        confirm.nth(i) for i in range(confirm.count()) if confirm.nth(i).is_visible()
    ]
    if len(visible_confirms) != 1:
        details = portal.locator("button").evaluate_all("""els => els.map(el => ({
          cls: String(el.className), text: (el.textContent || '').trim(),
          title: el.getAttribute('title'), top: el.getBoundingClientRect().top,
          visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
        }))""")
        raise RuntimeError(
            f"Telegram date picker confirmation button is ambiguous; buttons={details}"
        )
    confirm = visible_confirms[0]
    confirm.click()
    try:
        confirm.wait_for(state="hidden", timeout=3000)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError("Jump to Date confirmation did not close the calendar") from exc
    changed = False
    after_labels = before_labels
    after_dates: set[date] = set()
    for _ in range(40):
        page.wait_for_timeout(250)
        after_labels = _visible_date_labels(page)
        after_dates = {
            parsed for label in after_labels
            if (parsed := _date_from_label(label)) is not None
        }
        # Exact absolute match is the primary criterion.  A weekday label one
        # week back (e.g. jumping to last Tuesday just after midnight) resolves
        # to this week's Tuesday and can never equal target, so also accept the
        # bracket case: target inside the visible date range.  verify_anchor
        # remains the later hard gate for wrong-day landings.
        exact = target in after_dates
        bracket = bool(after_dates) and min(after_dates) <= target <= max(after_dates)
        if exact or bracket:
            changed = True
            break
    if not changed:
        raise RuntimeError(
            f"Jump to Date did not change visible DOM dates: "
            f"target={target.isoformat()} labels={after_labels}"
        )
    print(
        f"[rtss-cdp] jump_date_changed target={target.isoformat()} "
        f"before={before_labels} after={after_labels} absolute_dates="
        f"{[d.isoformat() for d in sorted(after_dates)]}"
    )
    print(f"[rtss-cdp] jump_date=ready target={target.isoformat()}")


def verify_anchor(page, target: date, timeout_ms: int = 5000) -> bool:
    """Verify the calendar jump landed on the requested date.

    A successful calendar click is not evidence that the virtualized message
    list contains the requested day.  Callers must treat False as
    ``ANCHOR_FAILED`` and must never turn it into a zero-count observation.
    """
    labels: list[str] = []
    seen: set[date] = set()
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        labels = _visible_date_labels(page)
        seen = {_date_from_label(label) for label in labels}
        seen.discard(None)
        if target in seen:
            break
        page.wait_for_timeout(250)
    ok = target in seen
    print(
        f"[rtss-cdp] verify_anchor target={target.isoformat()} "
        f"ok={int(ok)} labels={json.dumps(labels, ensure_ascii=True)} "
        f"seen={[d.isoformat() for d in sorted(seen)]}"
    )
    return ok


def _scroll_down(scroll, page) -> None:
    page.bring_to_front()
    box = scroll.bounding_box()
    if not box:
        raise RuntimeError("RTSS message scroll container has no bounding box")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    client_height = scroll.evaluate("el => el.clientHeight")
    step = max(1, int(client_height * SCROLL_OVERLAP_RATIO))
    page.mouse.wheel(0, step)
    page.wait_for_timeout(400)


def _harvest_day(page, target: date, max_local_steps: int = 15) -> list[dict]:
    """Harvest one calendar anchor only; never build a long scroll chain."""
    scroll = _scrollable(page)
    seen: dict[str, dict] = {}

    def harvest() -> tuple[set[date], set[date]]:
        dates: set[date] = set()
        for row in _message_rows(page):
            title = str(row.get("dom_title") or "")
            msg_date = _date_from_title(title) or _date_from_label(str(row.get("date_label") or ""))
            if msg_date:
                dates.add(msg_date)
            if msg_date != target:
                continue
            text = clean_alert_text(str(row.get("raw_text") or ""))
            if not text:
                continue
            key = hashlib.sha256(f"{title}\n{text}".encode("utf-8", errors="replace")).hexdigest()
            seen[key] = {
                "message_key": key, "message_date": target.isoformat(),
                "dom_title": title, "raw_text": text, "source_url": page.url,
                "captured_at_hkt": now_hkt().isoformat(),
            }
        return dates, set(seen)

    # Telegram Web intermittently ignores a Jump to Date click (the DOM stays
    # at the previous position).  Bounded retry: the flow is idempotent and
    # verify_anchor still gates each landing downstream.
    last_jump_err: Exception | None = None
    for _attempt in range(4):
        try:
            _jump_to_date(page, target)
            last_jump_err = None
            break
        except RuntimeError as exc:
            last_jump_err = exc
            print(f"[rtss-cdp] jump_retry attempt={_attempt + 1} target={target.isoformat()}")
            if _attempt == 2:
                # Telegram Web A silently ignores Jump to Date once its client
                # state degrades after long sessions; a page reload restores
                # working jumps (verified live 2026-09-15).  The URL keeps the
                # RTSS fragment, so the client reopens the same channel.
                print("[rtss-cdp] jump_reload_page before final attempt")
                page.reload()
                for _ in range(20):
                    page.wait_for_timeout(1000)
                    if page.locator(".MessageList").count():
                        break
            else:
                page.wait_for_timeout(2000)
    if last_jump_err is not None:
        raise last_jump_err
    dates, _ = harvest()
    for i in range(max_local_steps):
        if any(d < target for d in dates):
            break
        _scroll_up(scroll, page)
        dates, _ = harvest()

    # Telegram Web intermittently ignores a Jump to Date click (the DOM stays
    # at the previous position).  Bounded retry: the flow is idempotent and
    # verify_anchor still gates each landing downstream.
    last_jump_err: Exception | None = None
    for _attempt in range(4):
        try:
            _jump_to_date(page, target)
            last_jump_err = None
            break
        except RuntimeError as exc:
            last_jump_err = exc
            print(f"[rtss-cdp] jump_retry attempt={_attempt + 1} target={target.isoformat()}")
            if _attempt == 2:
                # Telegram Web A silently ignores Jump to Date once its client
                # state degrades after long sessions; a page reload restores
                # working jumps (verified live 2026-09-15).  The URL keeps the
                # RTSS fragment, so the client reopens the same channel.
                print("[rtss-cdp] jump_reload_page before final attempt")
                page.reload()
                for _ in range(20):
                    page.wait_for_timeout(1000)
                    if page.locator(".MessageList").count():
                        break
            else:
                page.wait_for_timeout(2000)
    if last_jump_err is not None:
        raise last_jump_err
    dates, _ = harvest()
    for i in range(max_local_steps):
        if any(d > target for d in dates):
            break
        _scroll_down(scroll, page)
        dates, _ = harvest()
    print(f"[rtss-cdp] day={target.isoformat()} visited=1 count={len(seen)}")
    return sorted(seen.values(), key=lambda r: (r["dom_title"], r["message_key"]))


def _scrollable(page):
    loc = page.locator(".bubbles-scrollable, .MessageList.custom-scroll, .Transition.MessageList").first
    if loc.count():
        return loc
    return page.locator(
        "[class*='scrollable'][class*='y'], [style*='overflow-y']"
    ).first


def collect_rows(page, start: date, end: date, do_scroll: bool = True) -> list[dict]:
    scroll = _scrollable(page)
    if not scroll.count():
        raise RuntimeError("RTSS message scroll container not found")

    # 主路線：用 Telegram calendar 定位起日，再向下自然閱讀方向 harvest。
    if do_scroll:
        _jump_to_date(page, start)

    seen: dict[str, dict] = {}
    stable_rounds = 0
    for i in range(1 if not do_scroll else MAX_SCROLL_ROUNDS):
        rows = _message_rows(page)
        before = len(seen)
        dates_seen: list[date] = []
        for row in rows:
            title = str(row.get("dom_title") or "")
            msg_date = _date_from_title(title) or _date_from_label(str(row.get("date_label") or ""))
            if msg_date:
                dates_seen.append(msg_date)
            text = clean_alert_text(str(row.get("raw_text") or ""))
            if not text:
                continue
            key = hashlib.sha256(
                f"{title}\n{text}".encode("utf-8", errors="replace")
            ).hexdigest()
            seen[key] = {
                "message_key": key,
                "message_date": msg_date.isoformat() if msg_date else "",
                "dom_title": title,
                "raw_text": text,
                "source_url": page.url,
                "captured_at_hkt": now_hkt().isoformat(),
            }

        oldest = min(dates_seen) if dates_seen else None
        newest = max(dates_seen) if dates_seen else None
        scroll_top = scroll.evaluate("el => el.scrollTop")
        print(
            f"[rtss-cdp] harvest scrollTop={scroll_top} "
            f"oldest={oldest or '—'} newest={newest or '—'} rows={len(seen)}"
        )
        if len(seen) == before:
            stable_rounds += 1
        else:
            stable_rounds = 0
        if not do_scroll:
            break
        if newest and newest >= end:
            break
        if stable_rounds >= STABLE_ROUNDS_LIMIT:
            break

        try:
            _scroll_down(scroll, page)
        except PlaywrightTimeoutError:
            break

    result = []
    for row in seen.values():
        try:
            msg_date = date.fromisoformat(row["message_date"])
        except ValueError:
            continue
        if start <= msg_date <= end:
            result.append(row)
    return sorted(result, key=lambda r: (r["message_date"], r["dom_title"], r["message_key"]))


def write_density_report(rows: list[dict], start: date, end: date) -> Path:
    """Write a complete daily count table for H's coverage acceptance."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for row in rows:
        day = str(row.get("message_date") or "")
        if day:
            counts[day] = counts.get(day, 0) + 1
    path = OUT_DIR / f"rtss_density_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    lines = ["date,weekday,is_weekday,alert_count,flag\n"]
    day = start
    while day <= end:
        count = counts.get(day.isoformat(), 0)
        is_weekday = day.weekday() < 5
        flag = "normal" if 4 <= count <= 15 else "suspicious" if count else "zero_weekday" if is_weekday else "zero_non_weekday"
        lines.append(f"{day.isoformat()},{day.strftime('%A')},{int(is_weekday)},{count},{flag}\n")
        day += timedelta(days=1)
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _date_range(args) -> tuple[date, date]:
    # Supplying an explicit range is itself a range run.  Previously the
    # parser only consumed --from/--to when --backfill was also present, so
    # the documented command silently fell back to today_hkt().
    if args.backfill or args.from_date or args.to_date:
        if not args.from_date or not args.to_date:
            raise SystemExit("--backfill 必須同時提供 --from YYYY-MM-DD --to YYYY-MM-DD")
        return date.fromisoformat(args.from_date), date.fromisoformat(args.to_date)
    if args.date:
        d = date.fromisoformat(args.date)
    else:
        d = today_hkt()
    return d, d


def main() -> int:
    ap = argparse.ArgumentParser(description="由現有 Chrome CDP 只讀抓 RTSS 文字")
    ap.add_argument("--date", help="YYYY-MM-DD；預設 today_hkt()")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--from", dest="from_date", help="backfill 起日 YYYY-MM-DD")
    ap.add_argument("--to", dest="to_date", help="backfill 終日 YYYY-MM-DD")
    ap.add_argument("--no-scroll", action="store_true", help="只 harvest 當前 DOM，用於診斷")
    args = ap.parse_args()
    start, end = _date_range(args)
    if start > end:
        raise SystemExit("--from 不可晚於 --to")
    print(f"[rtss-cdp] target={start.isoformat()}")

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        pages = [p for context in browser.contexts for p in context.pages]
        candidates = [p for p in pages if "web.telegram.org" in p.url and RTSS_FRAGMENT in p.url]
        if not candidates:
            print("[rtss-cdp] RTSS Chrome page not found", file=sys.stderr)
            return 1
        page = candidates[0]
        _assert_client(page)
        rows: list[dict] = []
        if args.no_scroll:
            rows = collect_rows(page, start, end, do_scroll=False)
        else:
            # I 主路線：每一日獨立跳轉；不依賴任何 restore_latest 或長距離捲動。
            for offset in range((end - start).days + 1):
                day = start + timedelta(days=offset)
                if day.weekday() >= 5:
                    continue
                rows.extend(_harvest_day(page, day))
        alert_times = []
        for row in rows:
            try:
                row_date = date.fromisoformat(str(row.get("message_date") or ""))
            except ValueError:
                row_date = _date_from_title(str(row.get("dom_title") or "")) or \
                    _date_from_label(str(row.get("date_label") or ""))
            time_match = TIME_RE.search(str(row.get("raw_text") or ""))
            if row_date and time_match:
                alert_times.append(f"{row_date.isoformat()} {time_match.group(1)}")
        print(f"[rtss-cdp] raw_rows={len(rows)} latest_alert_ts={max(alert_times) if alert_times else '—'}")
        density_path = write_density_report(rows, start, end)
        print(f"[rtss-cdp] density_report={density_path}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_day: dict[str, list[dict]] = {}
    for row in rows:
        by_day.setdefault(row["message_date"].replace("-", ""), []).append(row)
    for day in (start + timedelta(days=i) for i in range((end - start).days + 1)):
        if day.weekday() >= 5:
            continue
        day_key = day.strftime("%Y%m%d")
        path = OUT_DIR / f"raw_dom_{day_key}.jsonl"
        existing: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                    # A previous per-day writer could leave a row under the
                    # wrong filename after a virtualized-DOM pass.  Never
                    # carry that cross-day contamination forward.
                    if str(item.get("message_date") or "") != day.isoformat():
                        continue
                    text = clean_alert_text(str(item.get("raw_text") or ""))
                    # Keep only actual alert bubbles; old raw files may contain
                    # Telegram view-count/local-time UI rows from before T1.
                    if item.get("message_key") and text and re.search(r"\(\s*HK\.?\s*\d{1,5}\s*\)", text, re.I):
                        item["raw_text"] = text
                        item["message_key"] = hashlib.sha256(
                            f"{item.get('dom_title', '')}\n{text}".encode("utf-8", errors="replace")
                        ).hexdigest()
                        existing[item["message_key"]] = item
                except json.JSONDecodeError:
                    print(f"[rtss-cdp] ignored malformed raw line: {path}", file=sys.stderr)
        for item in by_day.get(day_key, []):
            existing[item["message_key"]] = item
        path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in existing.values()),
            encoding="utf-8",
        )
        print(f"[rtss-cdp] {day_key}: {len(existing)} raw text messages -> {path}")
        if not existing:
            print(f"[rtss-cdp] WARNING: no RTSS text messages found for {day_key}", file=sys.stderr)
        if args.backfill or args.from_date or args.to_date:
            checkpoint = {"completed_dates": [], "last_message_id": ""}
            if CHECKPOINT_PATH.exists():
                try:
                    checkpoint = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            completed = set(checkpoint.get("completed_dates", []))
            completed.add(day.isoformat())
            checkpoint["completed_dates"] = sorted(completed)
            checkpoint["last_message_id"] = (existing[next(reversed(existing))].get("dom_message_id", "")
                                               if existing else checkpoint.get("last_message_id", ""))
            CHECKPOINT_PATH.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
