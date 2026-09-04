# Model card

- **Version:** `dc-h2h-v2.0.0`
- **Default mode:** paper trading
- **Prediction target:** full-time 90-minute score-derived binary markets
- **Markets:** Over 2.5, Under 2.5, BTTS Yes
- **Primary model:** regularized, time-weighted Dixon–Coles
- **Eligibility overlay:** exact four-year H2H window, `N >= 5`, freshness `<= 730 days`, weighted hit rate `>= 75%`
- **Decision rule:** minimum odds 1.45, minimum conservative EV 5%, minimum de-vig edge 3 percentage points
- **Stake rule:** quarter Kelly with per-bet, daily, open-risk and drawdown caps

## Excluded use

- Goals in both halves without a dedicated half-by-half intensity model
- Youth, academy, reserve, B/II and amateur competitions or teams
- In-play betting
- Any live staking before timestamp-correct out-of-sample calibration

## Material risks

- API coverage and bookmaker mapping vary by competition.
- Promoted teams may lack enough connected league history and are skipped.
- H2H eligibility can create selection bias; performance must be measured on the screened universe.
- Backtest ROI is rejected when odds lack a same-bookmaker ID and a provably pre-kickoff capture timestamp.
- Parameters can drift across seasons, managers and competition formats.
- Bookmaker limits, rejected stakes and execution delay are not represented by theoretical ROI.
- Point ROI is insufficient evidence; the backtest withholds its day-cluster 95% interval below 30 matchdays, and live review requires a positive lower bound plus positive CLV.
