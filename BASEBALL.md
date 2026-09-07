# QuantBet Baseball v1

Baseball is a first-class sport inside the existing `h2h` repository. Football production remains isolated from the Baseball implementation.

## Current live-data phase

- API-Sports Baseball client at `https://v1.baseball.api-sports.io`
- persistent response cache
- per-run request budget and retry/backoff
- scheduled 30-minute Baseball ingestion during the active day
- up to 199 odds calls per run plus the daily schedule call
- league-diversity sampling so smaller leagues are not starved by MLB
- compact historical snapshots under `data/baseball/snapshots/`
- bookmaker and market coverage inventory under `data/baseball/market_coverage.json`
- Baseball intraday signal schema and paper alert layer

API-Sports Baseball currently advertises 77 leagues/cups, 30 bookmakers, odds coverage for major competitions including MLB, NPB, KBO and CPBL, and a Pro tier of 7,500 requests/day. The live collector therefore probes all available Baseball competitions returned by the daily schedule and prioritizes games carrying odds.

## Budget policy

The production subscription is 7,500 requests/day. The scheduled collector is deliberately capped at 200 requests per run and runs every 30 minutes from 06:00 through 23:30 Europe/Belgrade. That is 7,200 scheduled requests/day before retries; the remaining daily headroom is a safety reserve.

## Football-to-Baseball architecture

The Baseball system will reuse the Football operating pattern where it is structurally sound:

1. scheduled bulletin / baseline screening;
2. persistent prediction and odds snapshots;
3. frequent intraday refreshes after the bulletin;
4. immutable signal timestamps;
5. CLV capture and settlement;
6. paper-first alerts;
7. later production gating only after calibration and walk-forward validation.

The Baseball model itself is **not** assumed to be a copy of the Football model. Baseball gets a wider feature surface: starting pitcher, handedness, expected lineup, batter/pitcher splits, bullpen availability and workload, park, weather, rest/travel, team offensive/defensive rates, market state and player-level features where the feed supports them.

## Market scope

Initial market classes are:

- Moneyline / game winner;
- Run line / spread;
- Game total runs;
- player props only where the live odds payload proves sufficient coverage and stable settlement semantics.

The first model comparison will therefore be game-level markets plus a controlled player-prop experiment, rather than assuming props are available before validating the live bookmaker payload.

## Entry Decision

The eventual Baseball Entry Decision Engine will evaluate each snapshot independently. It may emit `WAIT`, `UPLATI SADA` or `SKIP`; an issued signal is never silently rewritten by later refreshes. The initial implementation is paper-only. The learning target is not a fixed number of hours before first pitch, but the optimal information/market state at which the model should enter.

## Next implementation stages

1. Validate the first live odds payloads and bookmaker/market schemas.
2. Normalize baseball games, teams, pitchers, lineups, player stats and odds.
3. Build Baseball probability/fair-odds models for the selected market classes.
4. Add calibration and walk-forward evaluation.
5. Feed predictions into the intraday scanner and `UPLATI SADA` paper alert layer.
6. Add Baseball-specific ledger/CLV tracking and outcome settlement.
7. Use the collected footprint to learn the Entry Decision policy.
