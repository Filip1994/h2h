# QuantBet v2.1 Hardening

## 1. H2H rule
H2H is **research telemetry only**. It contributes 0% to probability, EV, edge and selection. Production default is `H2H_TELEMETRY_ENABLED=false`, so the daily workflow does not spend an H2H API request per fixture.

When research mode is enabled, H2H is calculated against the same point-in-time cutoff and stored only so we can later test whether it adds incremental out-of-sample information.

## 2. Point-in-time data
Each generation run has one `decision_timestamp` and `data_cutoff`. Historical training records must be strictly older than that cutoff. Model and training caches include the cutoff, preventing silent reuse of a model trained on a different snapshot.

This is the key anti-look-ahead control.

## 3. Risk
`MAX_DAILY_RISK_PCT` is now a cumulative daily stake budget. A bet still counts toward today's budget after it settles. `MAX_OPEN_RISK_PCT` remains a separate current-exposure limit.

## 4. Audit trail
Each prediction records decision timestamp, data cutoff, odds capture timestamp, model version, calibration status and a rejection reason. A rejected market is a real research observation, not invisible data.

## 5. Email policy
The normal workflow sends **one daily bulletin** after generation, if Gmail is configured. Monitor and calibration do not send routine emails.

The daily bulletin can contain 0–5 new bets and includes portfolio state, API request count, data cutoff and a short explanation. A day with zero bets is expected and healthy.

## 6. Live gate
Live mode remains blocked until calibration is validated. Paper mode is the default. A positive backtest is not a promise of future profit; promotion requires out-of-sample evidence and monitoring.
