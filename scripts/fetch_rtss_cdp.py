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
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stockscan.io_utils import now_hkt, today_hkt

CDP_URL = "http://127.0.0.1:9222"
# Telegram Web uses the -100 prefix for channel peer IDs; older exports omit it.
# Match the stable numeric channel ID in either URL form.
RTSS_FRAGMENT = "2795969450"
OUT_DIR = Path("data/rtss")
TITLE_DATE_RE = re.compile(r"^(\d{1,2} [A-Za-z]+ \d{4}),")
TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}:\d{2})\b")


def _date_from_title(title: str) -> date | None:
    match = TITLE_DATE_RE.search(title or "")
    if not match:
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
    for fmt in ("%Y-%m-%d", "%B %d", "%b %d"):
        try:
            parsed = datetime.strptime(label, fmt).date() if fmt == "%Y-%m-%d" else \
                datetime.strptime(f"{today_hkt().year} {label}", f"%Y {fmt}").date()
            return parsed if fmt == "%Y-%m-%d" else parsed.replace(year=today_hkt().year)
        except ValueError:
            continue
    return None
    try:
        return datetime.strptime(match.group(1), "%d %B %Y").date()
    except ValueError:
        return None


def _message_rows(page) -> list[dict]:
    """Read message text/title only; no DOM action which changes Telegram state."""
    return page.locator(".message, .Message").evaluate_all(
        """els => els.map((el, index) => {
          const textEl = el.querySelector('.translatable-message, .text-content');
          const timeEl = el.querySelector('.time-inner, .time, .message-time');
          const dateEl = el.closest('.message-date-group')?.querySelector('.sticky-date');
          return {
            ordinal: index,
            raw_text: (textEl || el).innerText || (textEl || el).textContent || '',
            dom_title: timeEl ? (timeEl.getAttribute('title') || '') : '',
            date_label: dateEl ? (dateEl.innerText || dateEl.textContent || '') : '',
            dom_message_id: el.getAttribute('data-message-id') || ''
          };
        })"""
    )


def _scrollable(page):
    loc = page.locator(".bubbles-scrollable, .MessageList.custom-scroll, .Transition.MessageList").first
    if loc.count():
        return loc
    return page.locator(
        "[class*='scrollable'][class*='y'], [style*='overflow-y']"
    ).first


def collect_rows(page, start: date, end: date) -> list[dict]:
    scroll = _scrollable(page)
    if not scroll.count():
        raise RuntimeError("RTSS message scroll container not found")

    # 先由頻道目前位置回到底部，確保「今日」訊息已 render；只改 scrollTop，
    # 不 click、不 focus 訊息，唔會觸發已讀。
    scroll.evaluate("el => { el.scrollTop = el.scrollHeight; }")
    page.wait_for_timeout(500)

    seen: dict[str, dict] = {}
    stable_rounds = 0
    for _ in range(120):
        rows = _message_rows(page)
        before = len(seen)
        dates_seen: list[date] = []
        for row in rows:
            title = str(row.get("dom_title") or "")
            msg_date = _date_from_title(title) or _date_from_label(str(row.get("date_label") or ""))
            if msg_date:
                dates_seen.append(msg_date)
            text = " ".join(str(row.get("raw_text") or "").split())
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
        if len(seen) == before:
            stable_rounds += 1
        else:
            stable_rounds = 0
        if oldest and oldest <= start:
            break
        if stable_rounds >= 4:
            break

        try:
            scroll.evaluate("el => { el.scrollTop = 0; el.dispatchEvent(new Event('scroll', {bubbles: true})); }")
            page.wait_for_timeout(500)
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


def _date_range(args) -> tuple[date, date]:
    if args.backfill:
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
    args = ap.parse_args()
    start, end = _date_range(args)
    if start > end:
        raise SystemExit("--from 不可晚於 --to")

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        pages = [p for context in browser.contexts for p in context.pages]
        candidates = [p for p in pages if "web.telegram.org" in p.url and RTSS_FRAGMENT in p.url]
        if not candidates:
            print("[rtss-cdp] RTSS Chrome page not found", file=sys.stderr)
            return 1
        page = candidates[0]
        rows = collect_rows(page, start, end)
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

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_day: dict[str, list[dict]] = {}
    for row in rows:
        by_day.setdefault(row["message_date"].replace("-", ""), []).append(row)
    for day in (start + timedelta(days=i) for i in range((end - start).days + 1)):
        day_key = day.strftime("%Y%m%d")
        path = OUT_DIR / f"raw_dom_{day_key}.jsonl"
        existing: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                    if item.get("message_key"):
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
