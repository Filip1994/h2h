# QuantBet — data, history i audit guide

## 1. Četiri glavna istorijska sloja

### `bets.json`

**Decision ledger.** Samo stvarno izabrani betovi. Počinje kao PENDING i kasnije se enrichuje closing/result/CLV podacima.

Najvažnije grupe polja:

- identitet: fixture/event ID, teams, league, market;
- odluka: odd, bookmaker, model_probability, calibrated_probability, decision_probability, EV, edge;
- risk: stake, mode;
- H2H: enabled/available/status/snapshot/rate/n/effective_n/history kada postoji;
- lifecycle: PENDING/WIN/LOSS/SKIPPED/VOID/REVIEW, result, profit, settled_at;
- closing/CLV: closing odds, closing de-vig, capture timestamps, CLV.

### `predictions.json`

**Model/calibration ledger.** Beleži svaki modelovani market u skeniranom universe-u, ne samo selected bets.

To je fajl koji treba gledati kada pitaš:

> "Šta je model video, a zašto nije izabrao?"

`selected=false` + `rejection_reason` je posebno važno.

### `data/raw_api/YYYY-MM-DD.jsonl`

**Source evidence.** Svaki uspešan network API odgovor, sa timestampom, endpointom, parametrima, provenance i punim payloadom.

Cache hitovi se ne dupliraju kao network response.

### `data/h2h_snapshots.jsonl` + `data/h2h_outcomes.jsonl`

**H2H research evidence.** Snapshot čuva ono što je H2H sloj znao u trenutku odluke. Outcome kasnije dodaje konačan rezultat fixture-a i veže ga preko `h2h_snapshot_id`.

---

## 2. Point-in-time princip

Svaka generation odluka ima `decision_timestamp` i `data_cutoff`.

Model trening eksplicitno odbacuje svaki match koji je na ili posle cutoff-a. H2H takođe odbacuje buduće/istovremene mečeve.

Ovo je zaštita od look-ahead leakage-a.

Praktično:

```text
09:00 decision
|
+-- sme: podaci dostupni pre 09:00
+-- ne sme: rezultat/odds koji su nastali posle 09:00
```

---

## 3. H2H snapshot identity

`h2h_snapshot_id = SHA256(fixture_id | data_cutoff)`.

Zbog toga isti fixture + isti cutoff predstavlja isti canonical snapshot.

Snapshot je append-only i postojeći ID se ne dodaje drugi put.

---

## 4. Šta H2H snapshot sadrži

Snapshot nosi:

- fixture/team/league identitet;
- decision timestamp/data cutoff;
- `h2h_enabled`;
- `h2h_available`;
- `h2h_status`;
- eventualni error;
- weighted rates za Over/Under/BTTS;
- H2H `n`;
- effective N;
- flag da postoji recent H2H;
- listu H2H mečeva sa fixture ID, datumom, ligom, timovima, FT i HT score-om;
- source endpoint/request hash;
- capture timestamp.

Status može biti:

- `AVAILABLE`
- `INSUFFICIENT_HISTORY`
- `NO_RECENT_HISTORY`
- `API_ERROR`
- `PARSE_ERROR`
- `NOT_REQUESTED`

---

## 5. H2H outcome join

Kada prediction kasnije dobije konačan rezultat, `tools/persist_h2h.py` pronalazi njegov `h2h_snapshot_id` i dodaje outcome u `h2h_outcomes.jsonl`.

To omogućava budući research bez menjanja originalnog snapshot-a.

Možemo pitati:

- kakav je bio H2H signal u trenutku odluke;
- koliko je H2H bilo mečeva;
- koliko je effective N;
- koliko je H2H bilo sveže;
- koji market je H2H favorizovao;
- da li je finalni market outcome potvrdio H2H;
- da li je bet imao pozitivan CLV;
- da li H2H dodaje nešto preko DC + market baseline-a.

---

## 6. API archive

Raw archive je najbolji alat za debugging.

Ako bet izgleda čudno, ne treba odmah zaključiti da je model pogrešio. Prvo proveriti:

```text
API response
  -> parser
  -> filters
  -> model
  -> market quote
  -> decision
```

Archive je dnevni UTC JSONL i namenjen je da ostane append-only tokom observation perioda.

---

## 7. API usage history

`api_usage.json` predstavlja poslednji generation usage snapshot.

`api_usage_history.json` čuva poslednjih 90 usage zapisa.

Tu pratimo:

- request count;
- budget/working budget/reserve;
- remaining budget;
- cache hits/misses/hit rate;
- rate-limit events;
- HTTP errors;
- API/network errors;
- endpoint request counts;
- endpoint cache hits;
- broj novih betova.

To omogućava da merimo da li određeni API poziv stvarno kupuje informaciju vrednu njegovog troška.

---

## 8. Ledger lifecycle

```text
prediction -> PENDING
             |
             +--> selected -> bets.json PENDING
             |
             +--> not selected -> ostaje u predictions.json

PENDING bet
   |
   +--> closing snapshot
   |
   +--> WIN / LOSS
   +--> VOID
   +--> REVIEW
   +--> SKIPPED
```

Za betting ledger isti fixture se blokira kada postoji blocking status, čime se sprečava dupli future signal za istu utakmicu.

---

## 9. CLV lifecycle

Postoje dva nivoa closing evidence-a:

### Regular monitor

Do 120 minuta pre kickoff-a pokušava snapshot kod istog bookmaker-a.

### Dedicated T-5

Poseban capture pokušava quote približno pet minuta pre kickoff-a.

T-5 polja imaju prefiks `closing_5m_`.

CLV se računa kada postoji validan closing quote.

---

## 10. Calibration data lifecycle

`predictions.json` je source za calibration.

Samo settled binary predictions ulaze u calibration sample.

Po marketu:

```text
historical predictions
       |
       v
chronological sort
       |
       v
70% fit / 30% validation
       |
       +--> Brier
       +--> log-loss
       +--> ECE
       |
       v
accepted Platt or identity
```

Kalibracija ne sme retroaktivno da promeni istorijsku odluku koja je već bila napravljena.

---

## 11. Bankroll history

`bets.json` nosi pojedinačne profit/loss rezultate. Portfolio engine ih sortira hronološki po settlement-u i gradi equity curve.

Iz toga nastaju:

- current bank;
- total profit;
- total stake;
- ROI;
- win rate;
- completed count;
- open stake;
- daily stake;
- current drawdown.

Drawdown je odnos trenutne equity vrednosti prema prethodnom peak-u, a ne prosta suma poslednjih gubitaka.

---

## 12. Šta je dokaz čega

| Pitanje | Najbolji dokaz |
|---|---|
| Šta je API video? | `data/raw_api/` |
| Šta je H2H video? | `data/h2h_snapshots.jsonl` |
| Da li je H2H bio uključen? | prediction/snapshot `h2h_enabled` |
| Zašto je market odbijen? | `predictions.json.rejection_reason` |
| Zašto je bet izabran? | `bets.json` + odgovarajući prediction |
| Koliki je stake? | `bets.json` |
| Šta se kasnije desilo sa kvotom? | closing fields / T-5 fields |
| Da li je bet dobio/gubio? | `bets.json` settlement |
| Da li je model kalibrisan? | `calibration.json` |
| Koliko API trošimo? | `api_usage*.json` |
| Da li je daily bulletin završen? | `bulletin_health.json` |
| Da li H2H ima incremental signal? | H2H snapshot + outcomes + prediction/bet/CLV dataset |

---

## 13. Najvažnije istraživačko pravilo

Nikada ne gledati samo `bets.json` kada procenjujemo model.

`bets.json` je **selection-biased sample** — sadrži ono što je prošlo sve filtere.

`predictions.json` je širi universe i omogućava da uporedimo:

- selected vs rejected;
- high vs low H2H;
- different odds bands;
- markets;
- leagues;
- calibration buckets;
- CLV;
- realized outcomes.

Za ozbiljan zaključak o H2H-u potrebno je koristiti point-in-time snapshot-e i out-of-sample ishode, a ne retroaktivno birati samo H2H slučajeve koji izgledaju dobro.
