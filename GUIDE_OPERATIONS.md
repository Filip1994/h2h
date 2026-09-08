# QuantBet — operativni vodič

## Daily lifecycle

### 00:51 Europe/Belgrade
`daily.yml` pokreće daily bulletin. Pre generation-a `bulletin_health.py --guard` proverava da li je današnji bulletin već kompletno uspešan. Ručni dispatch može koristiti `force=true`.

### Generation

`python main.py generate --no-email`

Engine uzima trenutni business date, pravi immutable decision timestamp/data cutoff i poziva API. Daily workflow trenutno forsira `H2H_TELEMETRY_ENABLED=true`.

### Nakon generation-a

Workflow commituje:

- `bets.json`
- `predictions.json`
- `calibration.json`
- `ledger_meta.json`
- `api_usage.json`
- `api_usage_history.json`
- `data/raw_api/*`

Tek nakon uspešnog commit-a šalje bulletin email. Zatim piše `bulletin_health.json` SUCCESS marker.

## Monitor

`monitor.yml` trenutno radi svakih 5 minuta.

Za PENDING betove do 120 min pre kickoff-a pokušava da uhvati isti market kod istog bookmaker-a. Posle kickoff-a + 90 min proverava fixture status i settlement.

## T-5 closing

`capture-closing` hvata namenski snapshot u prozoru približno T-8 do T-2 minuta. Ovaj snapshot je odvojen od ranijeg monitor snapshot-a.

## Settlement

- FT/AET/PEN -> obračun market outcome-a;
- CANC/ABD -> VOID;
- AWD/WO -> REVIEW;
- nevalidan/nepotpun score -> REVIEW.

Prediction rows dobijaju `SETTLED` + binary outcome kada je rezultat validan. Bet rows dobijaju WIN/LOSS + profit.

## Calibration

`calibrate.yml` / `python main.py calibrate` radi hronološki 70/30 Platt calibration po marketu. Minimum je 200 observations. Platt se prihvata samo ako ne pogorša Brier i log-loss na held-out delu, a ECE mora biti <=5%.

## H2H research

`h2h-research.yml` se pokreće nakon uspešnih state-changing workflow-a i radi `tools/persist_h2h.py` + health check.

Rezultat se čuva u append-only:

- `data/h2h_snapshots.jsonl`
- `data/h2h_outcomes.jsonl`

## Files to inspect when something looks wrong

### "Zašto je dao ovaj bet?"

1. `bets.json`
2. odgovarajući `predictions.json` zapis
3. `ledger_meta.json`
4. `data/h2h_snapshots.jsonl` preko `h2h_snapshot_id`
5. `data/raw_api/YYYY-MM-DD.jsonl`

### "Zašto nije dao bet?"

Traži odgovarajući prediction u `predictions.json` i `rejection_reason`.

### "Da li je API radio?"

1. `api_usage.json`
2. `api_usage_history.json`
3. `data/raw_api/`
4. generation health

### "Da li je bulletin stvarno završen?"

`bulletin_health.json`.

### "Da li je rezultat pravilno settlement-ovan?"

`bets.json` + `predictions.json` + fixture API archive + settlement health.

## Safety rules

- Default je PAPER mode.
- Ne ručno menjati istorijske betove radi lepšeg rezultata.
- Ne brisati raw API/H2H research archive tokom observation perioda.
- Ne tretirati H2H kao dokaz edge-a bez OOS analize.
- Ne tretirati point ROI kao dokaz profitabilnosti.
- Ne uključivati live dok calibration/risk/research gate nije validan.

## Current configuration that matters most

- timezone: `Europe/Belgrade`
- initial bank: 50,000 RSD
- minimum odds: 1.45
- max overround: 20%
- minimum EV: 5%
- minimum probability edge: 3pp
- probability haircut: 3pp
- Kelly: 25% full Kelly
- max bet: 1% bankroll
- max daily new risk: 3%
- max open risk: 5%
- drawdown reduction: 5%
- drawdown stop: 10%
- H2H: 4-year window, >=5 matches, >=1 match in last 730 days, weighted with xi=0.0015
- calibration minimum: 200 per market

## Current operational warning

Documentation and runtime have drifted. The old README still describes a 06:00 UTC daily schedule and an H2H selection gate, while current runtime has 00:51 Europe/Belgrade and H2H telemetry is not used as the production probability/EV input. Keep this distinction in mind until docs cleanup is complete.
