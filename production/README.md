# Production

This folder defines the human-facing Production contract.

## Production only

1. `main.py generate` creates the daily Production picks and sends the email.
2. `main.py capture-odds` captures the allowed bookmaker quotes for the next 72 hours.
3. `main.py monitor` settles finished Production bets.
4. `tools/build_production_view.py` turns immutable odds snapshots + `bets.json` into `production_dashboard.json`.
5. The dashboard shows only hard observations: Opening, Pick, Live, Closing and CLV.

Missing data is `null` in the data and `—` in the dashboard. No fallback bookmaker is allowed.

The mathematical model remains in `src/quantbot/` and is frozen during the Production stabilization phase.