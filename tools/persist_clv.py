from __future__ import annotations

import argparse
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
from quantbot.persistence import (
    OddsSnapshotStore,
    record_prediction_quote,
    snapshot_id,
)
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
        return (
            int(item["event_id"]),
            str(item["market"]),
            int(item["bookmaker_id"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def entries(settings: Settings) -> int:
    predictions = load_list(settings.predictions_file)
    bets = BetStore(settings.bets_file).load()
    bet_by_key = {key(b): str(b["id"]) for b in bets if key(b) and b.get("id")}
    store = OddsSnapshotStore(SNAP)
    changed = 0

    for prediction in predictions:
        if (
            prediction.get("entry_snapshot_id")
            or not prediction.get("odd")
            or not prediction.get("opposite_odd")
        ):
            continue

        snapshot = record_prediction_quote(
            settings,
            prediction,
            bet_id=bet_by_key.get(key(prediction)),
            store=store,
        )

        if snapshot:
            prediction["signal_id"] = str(
                prediction.get("signal_id") or prediction.get("id")
            )
            prediction["entry_snapshot_id"] = snapshot
            changed += 1

    if changed:
        atomic_write_json(settings.predictions_file, predictions)
        bets = BetStore(settings.bets_file).load()
        pred_map = {key(p): p for p in predictions if key(p)}

        for bet in bets:
            prediction = pred_map.get(key(bet))
            if prediction and prediction.get("entry_snapshot_id"):
                bet["prediction_id"] = prediction.get("id")
                bet["signal_id"] = prediction.get("signal_id") or prediction.get("id")
                bet["entry_snapshot_id"] = prediction.get("entry_snapshot_id")

        BetStore(settings.bets_file).save(bets)

    return changed


def intermediate(settings: Settings) -> int:
    predictions = load_list(settings.predictions_file)
    by_fixture: dict[int, list[dict]] = {}

    for prediction in predictions:
        try:
            by_fixture.setdefault(int(prediction["event_id"]), []).append(prediction)
        except (KeyError, TypeError, ValueError):
            continue

    store = OddsSnapshotStore(SNAP)
    changed = 0

    for path in sorted(RAW.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                fixture_id = int((record.get("params") or {})["fixture"])
                captured = datetime.fromisoformat(str(record["captured_at"])).astimezone(UTC)
                raw = (record.get("payload") or {}).get("response")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue

            if record.get("endpoint") != "odds" or not isinstance(raw, list):
                continue

            for prediction in by_fixture.get(fixture_id, []):
                try:
                    bookmaker_id = int(prediction["bookmaker_id"])
                    market = Market.parse(str(prediction["market"]))
                except (KeyError, TypeError, ValueError):
                    continue

                quotes = extract_best_quotes(
                    raw,
                    bookmaker_priority=(bookmaker_id,),
                    allow_any_bookmaker=False,
                    captured_at=captured,
                    only_bookmaker_id=bookmaker_id,
                )
                quote = quotes.get(market)

                if quote is None or not (0 <= quote.overround <= settings.max_market_overround):
                    continue

                if store.append_quote(
                    quote,
                    fixture_id=fixture_id,
                    snapshot_type="INTERMEDIATE",
                    prediction_id=str(prediction.get("id") or "") or None,
                    signal_id=str(prediction.get("signal_id") or prediction.get("id") or "") or None,
                    captured_by="raw_api_archive",
                ):
                    changed += 1

    return changed


def t5(settings: Settings) -> int:
    bets = BetStore(settings.bets_file).load()
    predictions = {
        key(prediction): prediction
        for prediction in load_list(settings.predictions_file)
        if key(prediction)
    }
    store = OddsSnapshotStore(SNAP)
    changed = 0

    for bet in bets:
        if (
            bet.get("t5_snapshot_id")
            or bet.get("closing_5m_odd") is None
            or bet.get("closing_5m_odds_captured_at") is None
        ):
            continue

        try:
            opposite = float(bet.get("closing_5m_opposite_odd") or 0)
            if opposite <= 1:
                continue
            quote = OddsQuote(
                Market.parse(str(bet["market"])),
                float(bet["closing_5m_odd"]),
                opposite,
                int(bet["bookmaker_id"]),
                str(bet.get("bookmaker") or ""),
                datetime.fromisoformat(str(bet["closing_5m_odds_captured_at"])).astimezone(UTC),
            )
        except (KeyError, TypeError, ValueError):
            continue

        prediction = predictions.get(key(bet))
        signal = str(
            (prediction or {}).get("signal_id")
            or (prediction or {}).get("id")
            or bet.get("signal_id")
            or bet.get("prediction_id")
            or ""
        ) or None

        snapshot = store.append_quote(
            quote,
            fixture_id=int(bet["event_id"]),
            snapshot_type="T5",
            prediction_id=(prediction or {}).get("id"),
            bet_id=str(bet["id"]),
            signal_id=signal,
            captured_by="capture-closing",
        )

        if snapshot:
            bet["t5_snapshot_id"] = snapshot
            changed += 1

    if changed:
        BetStore(settings.bets_file).save(bets)

    return changed


def closing(settings: Settings) -> int:
    """Persist only the real closing quote captured by the existing monitor."""
    bets = BetStore(settings.bets_file).load()
    snapshots = load_snapshots()
    store = OddsSnapshotStore(SNAP)
    existing_ids = {str(snapshot["snapshot_id"]) for snapshot in snapshots if snapshot.get("snapshot_id")}
    changed = 0

    for bet in bets:
        if str(bet.get("status", "")).upper() not in TERMINAL:
            continue

        if any(
            bet.get(field) is None
            for field in (
                "closing_odd",
                "closing_opposite_odd",
                "closing_market_probability_devig",
                "closing_odds_captured_at",
            )
        ):
            bet["clv_status"] = "NOT_COMPUTABLE"
            continue

        try:
            kickoff = datetime.fromisoformat(str(bet["kickoff"])).astimezone(UTC)
            captured_at = datetime.fromisoformat(str(bet["closing_odds_captured_at"])).astimezone(UTC)
            odd = float(bet["closing_odd"])
            opposite_odd = float(bet["closing_opposite_odd"])
            devig_probability = float(bet["closing_market_probability_devig"])
            if odd <= 1 or opposite_odd <= 1 or captured_at > kickoff:
                raise ValueError("invalid canonical closing quote")
            market = Market.parse(str(bet["market"]))
            bookmaker_id = int(bet["bookmaker_id"])
            fixture_id = int(bet["event_id"])
        except (KeyError, TypeError, ValueError):
            bet["clv_status"] = "NOT_COMPUTABLE"
            continue

        entry = next(
            (snapshot for snapshot in snapshots if snapshot.get("snapshot_id") == bet.get("entry_snapshot_id")),
            None,
        )
        prediction_id = bet.get("prediction_id") or (entry or {}).get("prediction_id")
        signal_id = bet.get("signal_id") or (entry or {}).get("signal_id") or prediction_id
        overround = (1.0 / odd) + (1.0 / opposite_odd) - 1.0

        canonical = {
            "fixture_id": fixture_id,
            "market": market.value,
            "bookmaker_id": bookmaker_id,
            "bookmaker": str(bet.get("bookmaker") or bookmaker_id),
            "selection": market.value,
            "odd": round(odd, 4),
            "opposite_odd": round(opposite_odd, 4),
            "devig_probability": round(devig_probability, 6),
            "overround": round(overround, 6),
            "odds_captured_at": captured_at.isoformat(),
            "snapshot_type": "CLOSING",
            "prediction_id": str(prediction_id) if prediction_id else None,
            "bet_id": str(bet["id"]),
            "signal_id": str(signal_id) if signal_id else None,
            "source_endpoint": "odds",
            "source_request_hash": None,
            "captured_by": "monitor-closing-capture",
        }

        canonical_id = snapshot_id(canonical)
        if canonical_id not in existing_ids:
            store.append(canonical)
            existing_ids.add(canonical_id)
            snapshots.append({**canonical, "snapshot_id": canonical_id})
            changed += 1

        bet["closing_snapshot_id"] = canonical_id

        if entry:
            bet["clv_odds_pct"] = round(float(entry["odd"]) / float(canonical["odd"]) - 1, 6)
            bet["clv_probability_pp"] = round(float(canonical["devig_probability"]) - float(entry["devig_probability"]), 6)
            bet["clv_status"] = "COMPUTABLE"
        else:
            bet["clv_status"] = "NOT_COMPUTABLE"

    BetStore(settings.bets_file).save(bets)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("entry", "intermediate", "t5", "closing", "all"))
    phase = parser.parse_args().phase
    settings = Settings.from_env(ROOT)
    if phase in {"entry", "all"}:
        print(f"ENTRY snapshots: {entries(settings)}")
    if phase in {"intermediate", "all"}:
        print(f"INTERMEDIATE snapshots: {intermediate(settings)}")
    if phase in {"t5", "all"}:
        print(f"T5 snapshots: {t5(settings)}")
    if phase in {"closing", "all"}:
        print(f"CLOSING snapshots: {closing(settings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())