# QuantBet Roadmap & Operating Goals

**Date:** 2026-09-11  
**Scope:** Football QuantBet Production  
**Current mode:** PAPER_MODE / production validation

## 1. North Star

Build QuantBet into a reliable, auditable football decision system where:

1. the model produces independently qualified signals;
2. the exact bookmaker price at decision time is persisted;
3. post-pick odds are observed at the required cadence;
4. Closing odds and CLV are captured without fabrication;
5. settlement is automatic and immutable;
6. the dashboard reflects the same underlying production truth;
7. research is separated from Production until it passes an explicit promotion gate;
8. live-money deployment happens only after sufficient out-of-sample evidence and operational reliability.

The objective is **not** to maximize the number of picks. The objective is to prove whether the system has durable predictive and market-timing edge.

---

# 2. SHORT TERM — Day-to-Day Operating Plan

## Every day

### A. Production health

- Verify the Daily Production generation completed.
- Verify the Daily Bulletin was delivered.
- Verify every active pick has a valid immutable decision packet.
- Verify the odds collector is running and the latest scan is fresh.
- Verify API budget usage and remaining quota.
- Verify no workflow is silently failing or being replaced by another workflow.

### B. Active picks

For every active Production pick:

- `FIRST SEEN` must be a real persisted observation.
- `PICK` must equal the exact bulletin/decision odds.
- `CURRENT` must be a real observation after PICK and before kickoff.
- `CLOSING` remains `—` until kickoff has passed and a valid closing observation exists.
- No bookmaker substitution.
- No fabricated odds.
- No manual rewriting of historical observations.

### C. Execution decisions

The only manual Production actions should be:

- **TAKE** — leave the qualifying pick active.
- **SKIP** — use the controlled skip mechanism; preserve the decision packet and mark the bet `SKIPPED`.

Do not manually edit `bets.json` to change individual production records.

### D. After matches

- Confirm settlement.
- Confirm WIN/LOSS and P/L.
- Confirm Closing exists where the collector captured it.
- Confirm CLV calculation.
- Investigate missing lifecycle stages rather than filling them manually.

### E. Rule for engineering changes

No model or strategy change is allowed merely because one pick won, lost, moved, or looked wrong.

Operational bugs are fixed immediately. Strategy changes require evidence.

---

# 3. WEEKLY PLAN

Run one structured QuantBet review every week.

## Weekly operating review

### Reliability

Track:

- Daily Bulletin success rate.
- Odds collector success rate.
- Settlement success rate.
- Dashboard deployment success rate.
- Number of stale scans.
- Number of missing Closing observations.
- API requests used vs available quota.
- Number of manual interventions.

**Goal:** production should increasingly run without manual repair.

### Betting / market review

For all completed Production bets:

- Pick odds.
- Closing odds.
- CLV.
- Model probability.
- De-vig market probability.
- Decision probability.
- EV at entry.
- Result.
- P/L.

Do not judge the model primarily from short-run ROI. CLV and out-of-sample calibration are leading diagnostics; realized P/L is a noisy lagging metric.

### Model review

Weekly:

- Run chronological calibration evaluation.
- Check calibration by market.
- Check sample size.
- Check probability drift.
- Check whether the model's strongest signals remain directionally credible.

**Default:** freeze the Production model unless a predefined evidence threshold is met.

### Research queue

Maintain a small research queue only:

1. calibration;
2. market timing;
3. signal strength;
4. league/market segmentation;
5. model-vs-market diagnostics.

Do not add features simply because they are interesting.

---

# 4. MONTHLY PLAN — SEPTEMBER 2026

## Objective: Stabilize the production machine

September is primarily an **operational validation month**, not a model-rewrite month.

### Must achieve

- Single authoritative Production pipeline.
- Reliable Daily Bulletin.
- Reliable 72h odds lifecycle.
- Reliable settlement.
- Reliable skip mechanism.
- Single authoritative dashboard deployment path.
- Correct Opening/Pick/Current/Closing semantics.
- Railway raw-data archive operating without becoming an accidental second source of truth.
- No destructive manual edits to production state.

### Exit criteria

QuantBet should be able to run for a sustained period without requiring manual repair of:

- `bets.json`;
- odds observations;
- lifecycle stages;
- settlement;
- dashboard deployment.

---

# 5. OCTOBER 2026 GOAL

## Objective: Move from "working system" to "measurable system"

By the end of October, QuantBet should have a clean enough production dataset to answer:

> **Does the model consistently identify prices that subsequently move in our favor?**

### October targets

#### Data

- Build a materially larger clean Production observation history.
- Preserve exact Pick and Closing odds.
- Establish reliable CLV statistics.
- Establish market-by-market and league-by-league diagnostics.

#### Model

- Complete chronological out-of-sample calibration evaluation.
- Identify markets where calibration is strongest/weakest.
- Measure probability error, not only win rate.
- Freeze versions and record model identity for every Production decision.

#### Market timing

Measure:

- Pick → 6h movement.
- Pick → 3h movement.
- Pick → 1h movement.
- Pick → Closing movement.

This determines whether QuantBet is finding value early, late, or inconsistently.

#### Operations

Target:

- near-zero manual production intervention;
- no silent stale dashboard;
- no duplicate deployment path;
- no unexplained missing lifecycle stages;
- automatic settlement and archival.

### October decision gate

At the end of October, choose one of three paths:

**A. Promote / expand research** — evidence is strong enough to increase confidence and scope.

**B. Continue paper trading** — system is reliable but statistical evidence is still insufficient.

**C. Rework model/strategy** — evidence shows systematic calibration, CLV, or segmentation problems.

No live-money promotion based on ROI from a small sample.

---

# 6. NOVEMBER–DECEMBER 2026

## Objective: Build statistical confidence

After operational stabilization:

- accumulate a larger OOS sample;
- evaluate CLV distribution;
- evaluate calibration by probability bucket;
- evaluate performance by market;
- evaluate performance by league tier;
- measure drawdown behavior;
- test robustness against odds movement and missing observations;
- formalize research-to-production promotion criteria.

The key output is a **QuantBet evidence base**, not more UI.

---

# 7. 2027 LONG-TERM GOAL

## Objective: QuantBet becomes a research-grade, production-grade betting system

By 2027, the desired architecture is:

`Data → Model → Market → Decision → Execution → Observation → Settlement → Research`

with each layer independently auditable.

### 2027 priorities

#### 1. Data infrastructure

- Railway/Postgres becomes the durable historical store where appropriate.
- Raw API evidence remains archived.
- Production observations become queryable without loading large JSON files into every workflow.
- Data retention and provenance are explicit.

#### 2. Model research

- Versioned model families.
- Reproducible training datasets.
- Chronological OOS evaluation.
- Market-specific calibration.
- Drift detection.
- Controlled model promotion.

#### 3. Market intelligence

QuantBet should know not only:

> "Is this bet +EV?"

but also:

> "Is this price likely to remain available, move, or disappear before kickoff?"

That makes market timing a first-class research problem.

#### 4. Portfolio intelligence

Eventually evaluate:

- correlated exposure;
- market concentration;
- league concentration;
- drawdown regimes;
- optimal capital allocation;
- stake sizing robustness.

Risk controls remain authoritative over model enthusiasm.

#### 5. Live-money gate

Live deployment is permitted only when all required gates are satisfied:

- operational reliability;
- sufficient OOS sample;
- acceptable calibration;
- positive and persistent CLV evidence;
- acceptable drawdown behavior;
- stable model identity;
- reproducible decision provenance;
- tested settlement;
- tested failure recovery;
- explicit approval of the promotion gate.

`PAPER_MODE=true` remains the default until that gate is genuinely passed.

---

# 8. What We Will NOT Do

To keep QuantBet focused:

- No endless dashboard redesign.
- No unnecessary microservices.
- No strategy changes after individual wins/losses.
- No manual manipulation of historical Production records.
- No bookmaker substitution to make lifecycle data look complete.
- No fake Closing odds.
- No expanding into many markets before the current core is validated.
- No live-money deployment because the dashboard looks good.
- No architecture expansion before the current pipeline proves its value.

---

# 9. Priority Stack

When there is a choice, use this order:

1. **Data integrity**
2. **Production reliability**
3. **Correct odds lifecycle / CLV**
4. **Out-of-sample evidence**
5. **Model improvement**
6. **Market timing research**
7. **Portfolio/risk optimization**
8. **UI / presentation**

The system should become **more trustworthy before it becomes more sophisticated**.

---

# 10. Definition of Success

QuantBet is successful when we can look back at a large historical sample and reconstruct, for every Production decision:

- what the model believed;
- what the market price was;
- what price we actually selected;
- what happened to the price afterward;
- what the closing price was;
- whether we had CLV;
- whether the bet won or lost;
- how much capital was exposed;
- and why the system made the decision.

Only after that evidence is strong should the central question become:

> **How much money can QuantBet safely scale?**
