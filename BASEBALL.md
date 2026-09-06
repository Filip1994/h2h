# QuantBet Baseball v1

Baseball is being added as a first-class sport inside the existing `h2h` repository. Football production remains untouched while Baseball is developed on `feature/baseball-v1`.

## Phase 1

- API-Sports Baseball client at `https://v1.baseball.api-sports.io`
- persistent response cache
- per-run request budget
- retry/backoff handling
- adaptive budget allocation based on time to first pitch
- offline unit tests
- no paid API calls are made by CI

## API budget

Target production tier: API-Sports Baseball PRO, 7,500 requests/day. The budget is configurable through `BASEBALL_API_REQUEST_BUDGET`; the default is 7,500.

We do **not** activate the subscription or add live GitHub Actions ingestion until the raw response schema is validated. Until then, tests remain offline.

## Betting timing rule

The bulletin timestamp is the official Baseball entry timestamp. The pre-game refresh layer exists to improve the information available before the bulletin and to measure subsequent lineup/pitcher/market changes and CLV. It must not silently rewrite an already-issued bet.

## Next implementation stages

1. Validate live API responses and endpoint schemas.
2. Build raw-data snapshots and normalized baseball entities.
3. Add pitcher, batting, bullpen, lineup, park/weather and market features.
4. Build pre-bet probability and fair-odds model.
5. Add calibration and walk-forward evaluation.
6. Add Baseball-specific ledger/CLV tracking.
7. Add a scheduled Baseball bulletin workflow after the API subscription is activated.
