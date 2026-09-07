from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbot.config import Settings
from quantbot.markets import extract_best_quotes
from quantbot.persistence import OddsSnapshotStore, record_prediction_quote, snapshot_id
from quantbot.storage import BetStore, atomic_write_json
from quantbot.types import Market, OddsQuote

SNAP = ROOT / "data" / "odds_snapshots.jsonl"
RAW = ROOT / "data" / "raw_api"
TERMINAL = {"WIN", "LOSS", "VOID", "REVIEW", "SKIPPED"}


def load_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def load_snapshots() -> list[dict]:
    if not SNAP.exists():
        return []
    out = []
    for line in SNAP.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def key(item: dict) -> tuple[int, str, int] | None:
    try:
        return int(item["event_id"]), str(item["market"]), int(item["bookmaker_id"])
    except (KeyError, TypeError, ValueError):
        return None


def entries(settings: Settings) -> int:
    predictions = load_list(settings.predictions_file)
    bets = BetStore(settings.bets_file).load()
    bet_by_key = {key(b): str(b["id"]) for b in bets if key(b) and b.get("id")}
    store = OddsSnapshotStore(SNAP)
    changed = 0
    for p in predictions:
        if p.get("entry_snapshot_id") or not p.get("odd") or not p.get("opposite_odd"):
            continue
        sid = record_prediction_quote(settings, p, bet_id=bet_by_key.get(key(p)), store=store)
        if sid:
            p["signal_id"] = str(p.get("signal_id") or p.get("id"))
            p["entry_snapshot_id"] = sid
            changed += 1
    if changed:
        atomic_write_json(settings.predictions_file, predictions)
        bets = BetStore(settings.bets_file).load()
        pred_map = {key(p): p for p in predictions if key(p)}
        for b in bets:
            p = pred_map.get(key(b))
            if p and p.get("entry_snapshot_id"):
                b["prediction_id"] = p.get("id")
                b["signal_id"] = p.get("signal_id") or p.get("id")
                b["entry_snapshot_id"] = p.get("entry_snapshot_id")
        BetStore(settings.bets_file).save(bets)
    return changed


def intermediate(settings: Settings) -> int:
    predictions = load_list(settings.predictions_file)
    by_fixture: dict[int, list[dict]] = {}
    for p in predictions:
        try:
            by_fixture.setdefault(int(p["event_id"]), []).append(p)
        except (KeyError, TypeError, ValueError):
            pass
    store = OddsSnapshotStore(SNAP)
    changed = 0
    for path in sorted(RAW.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                fixture_id = int((r.get("params") or {})["fixture"])
                captured = datetime.fromisoformat(str(r["captured_at"])).astimezone(UTC)
                raw = (r.get("payload") or {}).get("response")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if r.get("endpoint") != "odds" or not isinstance(raw, list):
                continue
            for p in by_fixture.get(fixture_id, []):
                try:
                    bookmaker_id = int(p["bookmaker_id"])
                    market = Market.parse(str(p["market"]))
                except (KeyError, TypeError, ValueError):
                    continue
                quotes = extract_best_quotes(raw, bookmaker_priority=(bookmaker_id,), allow_any_bookmaker=False, captured_at=captured, only_bookmaker_id=bookmaker_id)
                q = quotes.get(market)
                if q is None or not (0 <= q.overround <= settings.max_market_overround):
                    continue
                if store.append_quote(q, fixture_id=fixture_id, snapshot_type="INTERMEDIATE", prediction_id=str(p.get("id") or "") or None, signal_id=str(p.get("signal_id") or p.get("id") or "") or None, captured_by="raw_api_archive"):
                    changed += 1
    return changed


def t5(settings: Settings) -> int:
    bets = BetStore(settings.bets_file).load()
    predictions = {key(p): p for p in load_list(settings.predictions_file) if key(p)}
    store = OddsSnapshotStore(SNAP)
    changed = 0
    for b in bets:
        if b.get("t5_snapshot_id") or b.get("closing_5m_odd") is None or b.get("closing_5m_odds_captured_at") is None:
            continue
        try:
            opposite = float(b.get("closing_5m_opposite_odd") or 0)
            if opposite <= 1:
                continue
            q = OddsQuote(Market.parse(str(b["market"])), float(b["closing_5m_odd"]), opposite, int(b["bookmaker_id"]), str(b.get("bookmaker") or ""), datetime.fromisoformat(str(b["closing_5m_odds_captured_at"])).astimezone(UTC))
        except (KeyError, TypeError, ValueError):
            continue
        p = predictions.get(key(b))
        sid = str((p or {}).get("signal_id") or (p or {}).get("id") or b.get("signal_id") or b.get("prediction_id") or "") or None
        snap = store.append_quote(q, fixture_id=int(b["event_id"]), snapshot_type="T5", prediction_id=(p or {}).get("id"), bet_id=str(b["id"]), signal_id=sid, captured_by="capture-closing")
        if snap:
            b["t5_snapshot_id"] = snap
            changed += 1
    if changed:
        BetStore(settings.bets_file).save(bets)
    return changed


def closing(settings: Settings) -> int:
    bets = BetStore(settings.bets_file).load()
    snapshots = load_snapshots()
    changed = 0
    for b in bets:
        if str(b.get("status", "")).upper() not in TERMINAL or b.get("closing_snapshot_id"):
            continue
        try:
            kickoff = datetime.fromisoformat(str(b["kickoff"])).astimezone(UTC)
            candidates = [s for s in snapshots if s.get("snapshot_type") in {"INTERMEDIATE", "T5"} and int(s.get("fixture_id")) == int(b["event_id"]) and str(s.get("market")) == str(b["market"]) and int(s.get("bookmaker_id")) == int(b["bookmaker_id"]) and datetime.fromisoformat(str(s["odds_captured_at"])).astimezone(UTC) <= kickoff]
        except (KeyError, TypeError, ValueError):
            continue
        if not candidates:
            b["clv_status"] = "NOT_COMPUTABLE"
            continue
        latest = max(candidates, key=lambda s: str(s["odds_captured_at"]))
        c = dict(latest)
        c["snapshot_type"] = "CLOSING"
        c["captured_by"] = "closing-finalizer"
        c["prediction_id"] = b.get("prediction_id") or latest.get("prediction_id")
        c["bet_id"] = str(b["id"])
        c["signal_id"] = b.get("signal_id") or latest.get("signal_id")
        c["snapshot_id"] = snapshot_id(c)
        existing = {str(s.get("snapshot_id")) for s in snapshots}
        if c["snapshot_id"] not in existing:
            with SNAP.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(c, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            snapshots.append(c)
            changed += 1
        b["closing_snapshot_id"] = c["snapshot_id"]
        b["closing_odd"] = c["odd"]
        b["closing_opposite_odd"] = c["opposite_odd"]
        b["closing_market_probability_devig"] = c["devig_probability"]
        b["closing_odds_captured_at"] = c["odds_captured_at"]
        entry = next((s for s in snapshots if s.get("snapshot_id") == b.get("entry_snapshot_id")), None)
        if entry:
            b["clv_odds_pct"] = round(float(entry["odd"]) / float(c["odd"]) - 1, 6)
            b["clv_probability_pp"] = round(float(c["devig_probability"]) - float(entry["devig_probability"]), 6)
            b["clv_status"] = "COMPUTABLE"
        else:
            b["clv_status"] = "NOT_COMPUTABLE"
    BetStore(settings.bets_file).save(bets)
    return changed


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("entry", "intermediate", "t5", "closing", "all"))
    phase = parser.parse_args().phase
    settings = Settings.from_env(ROOT)
    if phase in {"entry", "all"}: print(f"ENTRY snapshots: {entries(settings)}")
    if phase in {"intermediate", "all"}: print(f"INTERMEDIATE snapshots: {intermediate(settings)}")
    if phase in {"t5", "all"}: print(f"T5 snapshots: {t5(settings)}")
    if phase in {"closing", "all"}: print(f"CLOSING snapshots: {closing(settings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
