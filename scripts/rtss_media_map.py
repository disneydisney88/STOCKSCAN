#!/usr/bin/env python
"""O1: map Telegram message IDs to original tt-media Cache Storage objects.

This script is read-only: it observes DOM/cache state and never clicks a
message or takes a screenshot.  The four mapping methods are measured
independently; sequence pairing is explicitly LOW confidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from stockscan.io_utils import now_hkt
from stockscan.rtss_board_ocr import classify_board_caption, extract_threshold_x

FETCHER_PATH = Path(__file__).with_name("fetch_rtss_cdp.py")
spec = importlib.util.spec_from_file_location("rtss_fetcher", FETCHER_PATH)
fetcher = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(fetcher)

FIELDS = ["message_id", "msg_ts_hkt", "board_text", "board_type", "threshold_x",
          "cache_url", "cache_key", "map_method", "map_confidence"]


def install_cache_probe(page) -> None:
    page.evaluate("""() => {
      window.__rtss_cache_hits = [];
      if (window.__rtss_cache_hooked) return;
      window.__rtss_cache_hooked = true;
      const oldMatch = Cache.prototype.match;
      Cache.prototype.match = async function(request, ...args) {
        const url = typeof request === 'string' ? request : request?.url || '';
        if (/photo|document/i.test(url)) window.__rtss_cache_hits.push(url);
        return oldMatch.call(this, request, ...args);
      };
    }""")


def dom_candidates(page, target: date) -> list[dict]:
    rows = page.locator(".message-list-item").evaluate_all("""els => els.map((el, i) => {
      const media = el.querySelector('.media-inner');
      if (!media) return null;
      const prior = els.slice(0, i).reverse().find(x => {
        const t = x.querySelector('.translatable-message, .text-content');
        return t && /價格(?:上升|下降)股票|价格(?:上升|下降)股票/.test(t.innerText || t.textContent || '');
      });
      const text = prior?.querySelector('.translatable-message, .text-content');
      const time = el.querySelector('.time-inner, .time, .message-time');
      const attrs = [...el.querySelectorAll('*')].flatMap(x => [...x.attributes].map(a => [a.name, a.value]));
      return {message_id: el.dataset.messageId || el.id.replace('message-', ''),
        msg_ts_hkt: time?.getAttribute('title') || '',
        board_text: (text?.innerText || text?.textContent || '').trim(),
        blob_src: el.querySelector('img.full-media')?.src || '', attrs};
    }).filter(Boolean)""")
    answer = []
    for row in rows:
        if fetcher._date_from_title(row["msg_ts_hkt"]) != target:
            continue
        board_type = classify_board_caption(row["board_text"])
        if board_type:
            row["board_type"] = board_type
            row["threshold_x"] = extract_threshold_x(row["board_text"])
            answer.append(row)
    return answer


def _scroll_collect(page, target: date) -> list[dict]:
    fetcher._jump_to_date(page, target)
    if not fetcher.verify_anchor(page, target):
        raise RuntimeError(f"ANCHOR_FAILED {target.isoformat()}")
    install_cache_probe(page)
    scroll = fetcher._scrollable(page)
    found: dict[str, dict] = {}
    for _ in range(36):
        for row in dom_candidates(page, target):
            found[row["message_id"]] = row
        fetcher._scroll_down(scroll, page)
        dates = [fetcher._date_from_title(x) for x in page.locator(
            ".message-list-item .time-inner, .message-list-item .time, .message-list-item .message-time"
        ).evaluate_all("els => els.map(e => e.getAttribute('title') || '')")]
        if any(d and d > target for d in dates):
            # One extra overlapping harvest is enough to avoid a boundary miss.
            for row in dom_candidates(page, target):
                found[row["message_id"]] = row
            break
    return list(found.values())


def _dom_direct(row: dict) -> tuple[str, str] | None:
    for name, value in row.get("attrs", []):
        if name in {"src", "data-src", "data-media-id", "data-document-id"} and re.search(
                r"(?:photo|document)[^\d]*(\d+)", value, re.I):
            return value, "dom_direct"
    return None


def _state_direct(page, row: dict) -> tuple[str, str] | None:
    state = page.evaluate("""id => {
      const needles = [window.__INITIAL_STATE__, window.__NEXT_DATA__, window.__APOLLO_STATE__];
      return needles.filter(Boolean).map(x => JSON.stringify(x)).find(x => x.includes(String(id))) || '';
    }""", row["message_id"])
    match = re.search(r"https?[^\" ]*(?:photo|document)[^\" ]*", state or "", re.I)
    return (match.group(0), "state_direct") if match else None


def _exact_cache_matches(page, rows: list[dict], hits: list[str]) -> dict[str, str]:
    """Return only byte-for-byte blob/cache matches, never order guesses."""
    urls = list(dict.fromkeys(u for u in hits if "size=x" in u or "photo" in u.lower()))
    if not urls:
        return {}
    payload = page.evaluate("""async ({rows, urls}) => {
      async function digest(response) {
        const bytes = new Uint8Array(await response.arrayBuffer());
        const hash = await crypto.subtle.digest('SHA-256', bytes);
        return [...new Uint8Array(hash)].map(x => x.toString(16).padStart(2,'0')).join('');
      }
      const cache = await caches.open('tt-media');
      const cacheHashes = {};
      for (const url of urls) {
        const response = await cache.match(url);
        if (response) cacheHashes[url] = await digest(response);
      }
      const result = {};
      for (const row of rows) {
        if (!row.blob_src || !row.blob_src.startsWith('blob:')) continue;
        try {
          const hash = await digest(await fetch(row.blob_src));
          const match = Object.entries(cacheHashes).find(([, value]) => value === hash);
          if (match) result[row.message_id] = match[0];
        } catch (_) {}
      }
      return result;
    }""", {"rows": rows, "urls": urls})
    return payload or {}


def map_day(page, target: date) -> list[dict]:
    rows = _scroll_collect(page, target)
    hits = page.evaluate("() => [...new Set(window.__rtss_cache_hits || [])]")
    exact = _exact_cache_matches(page, rows, hits)
    out = []
    for index, row in enumerate(rows):
        direct = _dom_direct(row)
        state = None if direct else _state_direct(page, row)
        if direct:
            url, method, confidence = direct[0], direct[1], "HIGH"
        elif state:
            url, method, confidence = state[0], state[1], "HIGH"
        elif row["message_id"] in exact:
            url, method, confidence = exact[row["message_id"]], "cache_bytes_sha256", "HIGH"
        elif index < len(hits):
            url, method, confidence = hits[index], "cache_request_order", "LOW"
        else:
            url, method, confidence = "", "unmapped", "LOW"
        out.append({"message_id": row["message_id"], "msg_ts_hkt": row["msg_ts_hkt"],
                    "board_text": row["board_text"], "board_type": row["board_type"],
                    "threshold_x": row["threshold_x"], "cache_url": url,
                    "cache_key": url.split("?")[0] if url else "",
                    "map_method": method, "map_confidence": confidence})
    print(f"[rtss-map] date={target.isoformat()} messages={len(rows)} cache_hits={len(hits)} exact={len(exact)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="O1 RTSS message/cache mapping")
    ap.add_argument("--dates", nargs="+", required=True, help="YYYY-MM-DD ...")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dates = [date.fromisoformat(value) for value in args.dates]
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(fetcher.CDP_URL)
        pages = [p for c in browser.contexts for p in c.pages
                 if "web.telegram.org" in p.url and fetcher.RTSS_FRAGMENT in p.url]
        if not pages:
            raise RuntimeError("BLOCKED: RTSS Telegram tab not found on CDP 9222")
        page = pages[0]
        fetcher._assert_client(page)
        all_rows = []
        for target in dates:
            all_rows.extend(map_day(page, target))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(all_rows)
    methods = {}
    for row in all_rows:
        methods.setdefault(row["map_method"], {"matched": 0, "total": 0})
        methods[row["map_method"]]["total"] += 1
        if row["cache_url"]: methods[row["map_method"]]["matched"] += 1
    qa = {"generated_at_hkt": now_hkt().isoformat(), "rows": len(all_rows), "methods": methods,
          "high": sum(row["map_confidence"] == "HIGH" for row in all_rows),
          "high_rate": (sum(row["map_confidence"] == "HIGH" for row in all_rows) / len(all_rows)
                        if all_rows else 0),
          "one_to_one": len({row["message_id"] for row in all_rows}) == len(all_rows),
          "cache_url_unique": len({row["cache_url"] for row in all_rows if row["cache_url"]}) ==
                              sum(bool(row["cache_url"]) for row in all_rows)}
    qa_path = out.with_suffix(".qa.json")
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "qa": str(qa_path), **qa}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
