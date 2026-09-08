from datetime import date
import sqlite3

from stockscan.events import events_after


def _make_db(path):
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE events (event_type TEXT, code5 TEXT, name TEXT, announce_date TEXT, key_date_1 TEXT, key_date_2 TEXT, price_1 REAL, price_2 REAL, ratio TEXT, agent TEXT, status TEXT, raw_json TEXT, date_parse_failed INTEGER)")
        con.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            ("GO", "00653", "A", "2026-08-12", None, None, None, None, None, None, "open", "{}", 0),
            ("GO", "00653", "B", "2026-12-31", None, None, None, None, None, None, "open", "{}", 0),
        ])


def test_events_after_returns_ordered_window(tmp_path):
    db = tmp_path / "events.db"
    _make_db(db)
    rows = events_after("00653.hk", date(2026, 7, 3), 180, db)
    assert len(rows) == 1
    assert rows[0]["announce_date"] == "2026-08-12"


def test_events_after_excludes_unparsed_dates(tmp_path):
    db = tmp_path / "events.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE events (event_type TEXT, code5 TEXT, name TEXT, announce_date TEXT, key_date_1 TEXT, key_date_2 TEXT, price_1 REAL, price_2 REAL, ratio TEXT, agent TEXT, status TEXT, raw_json TEXT, date_parse_failed INTEGER)")
        con.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", ("GO", "00001", "A", None, None, None, None, None, None, None, "open", "{}", 1))
    assert events_after("00001.hk", "2026-01-01", 30, db) == []
