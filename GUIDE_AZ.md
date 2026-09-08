# QuantBet H2H — vodič od A do Z

> Ovo je operativni opis onoga što **trenutno stvarno radi `main` branch**. Nije zamišljena specifikacija budućeg sistema. Ako se README razlikuje od koda/workflow-a, prednost ima ovaj vodič i aktuelni kod.

## 0. Najkraća slika

```text
GitHub Actions
    |
    v
API-Football -> današnje utakmice
    |
    +-> filteri (liga/timovi/status/vreme)
    |
    +-> H2H telemetry snapshot (ako je uključeno)
    |
    +-> istorijski mečevi -> Dixon-Coles trening
    |
    +-> score matrix -> Over 2.5 / Under 2.5 / BTTS Yes
    |
    +-> bookmaker odds -> paired de-vig
    |
    +-> calibration -> probability haircut
    |
    +-> EV + probability edge
    |
    +-> portfolio/Kelly/risk limits
    |
    v
bets.json + predictions.json + health/usage + email
    |
    +-> monitor / closing capture
    |
    +-> rezultat + CLV + settlement
    |
    +-> H2H research telemetry + outcomes
    |
    v
weekly calibration / research / dashboard
```

**Najvažnije:** H2H trenutno nije deo matematičke verovatnoće. Služi kao telemetry/research sloj. Model koji daje `model_probability` je Dixon-Coles; odluka se zasniva na toj verovatnoći, kalibraciji, tržišnim kvotama, EV/edge i risk pravilima.

---

## 1. Ko pokreće sistem

Glavni entry point je `main.py`.

Najvažnije komande:

- `python main.py generate --no-email` — generiše odluke bez slanja emaila;
- `python main.py send-report` — šalje poslednji generisani report;
- `python main.py monitor` — hvata pre-kickoff quote i radi settlement;
- `python main.py capture-closing` — namenski T-5 closing snapshot;
- `python main.py closing-report` — završni closing-day report;
- `python main.py calibrate` — refit kalibracije;
- `python main.py analytics` — portfolio metrike;
- `python main.py skip --id ...` — PENDING -> SKIPPED.

`main.py` takođe upisuje `ledger_meta.json`, API usage i generation health. To znači da odluka nije samo jedan JSON bet zapis; postoji i metadata trag o tome kada i u kom režimu je nastala.

---

## 2. Kada se povlači API

Dnevni workflow je `.github/workflows/daily.yml` i trenutno je zakazan za **00:51 Europe/Belgrade**. Pre generisanja proverava health marker da ne napravi drugi dnevni bulletin osim ako je run ručno forced.

Daily workflow radi:

1. checkout poslednjeg `main`;
2. Python 3.12;
3. `python main.py generate --no-email`;
4. commituje ledger + API archive;
5. tek nakon uspešnog commit-a šalje email;
6. upisuje `bulletin_health.json` kao SUCCESS.

Daily workflow eksplicitno postavlja `H2H_TELEMETRY_ENABLED="true"`. To je bitno jer je config default `false`, ali production daily workflow trenutno override-uje taj default.

API klijent (`src/quantbot/api.py`) ima:

- hard request budget 7.500 po run-u;
- rezervu 500 zahteva;
- najviše 3 pokušaja;
- exponential backoff za 429/5xx i mrežne greške;
- TTL cache;
- arhiviranje svakog uspešnog network API odgovora u `data/raw_api/YYYY-MM-DD.jsonl`;
- GitHub Actions provenance kada postoji.

Cache TTL-ovi:

| Poziv | TTL |
|---|---:|
| fixtures by date | 10 min |
| fixture by ID | 5 min |
| H2H | 12 h |
| league+season fixtures | 6 h |
| odds | 2 min |

Cache hit ne pravi novi raw API archive zapis.

---

## 3. Prvi filter: koje utakmice uopšte smeju u sistem

`filters.py` odbacuje:

- U17–U23 i slične youth kategorije;
- youth/junior/reserve/academy/amateur;
- B/II/second teams;
- određene niže/neprofesionalne kategorije;
- eksplicitno isključene zemlje iz konfiguracije.

Fixture mora biti `NS` ili `TBD`, i mora biti u vremenskom prozoru:

- daily: više od 15 minuta od odluke i najviše 24h unapred;
- intraday: isti minimum, ali najviše 6h unapred.

Fixture koji je već blokiran kroz `bets.json` takođe se preskače. Time isti fixture ne dobija drugi bet.

---

## 4. H2H: šta se tačno radi

Ako je H2H telemetry uključena, engine poziva:

`fixtures/headtohead?h2h=HOME_ID-AWAY_ID`

Zatim `h2h.py`:

1. uzima samo završene mečeve;
2. koristi tačan rolling prozor od 4 godine;
3. odbacuje mečeve pre cutoff-a ili posle decision timestamp-a;
4. primenjuje iste league/team exclusion filtere;
5. traži najmanje 5 H2H mečeva;
6. traži bar jedan meč u poslednjih 730 dana;
7. svakom meču daje težinu `exp(-xi * age_days)` sa `xi=0.0015`;
8. računa weighted hit-rate za svaki market;
9. računa effective sample size.

Podržani H2H marketi su isti kao production marketi:

- `OVER_2_5`
- `UNDER_2_5`
- `BTTS_YES`

### Važna razlika

H2H rate se **ne dodaje** na Dixon-Coles probability i ne menja EV direktno. H2H je informacija za research/telemetry.

U `bets.json`/`predictions.json` može da se vidi:

- `h2h_enabled`
- `h2h_available`
- `h2h_status`
- `h2h_snapshot_id`
- `h2h_rate`
- `h2h_n`
- `h2h_effective_n`
- `h2h_history` gde je dostupna.

Pored toga postoji append-only `data/h2h_snapshots.jsonl` koji čuva ceo snapshot i sve H2H mečeve. Nakon settlement-a `data/h2h_outcomes.jsonl` povezuje snapshot sa konačnim rezultatom.

To je osnova za kasnije pitanje: **da li H2H dodaje incremental OOS signal ili samo izgleda dobro retrospektivno?**

---

## 5. Dixon-Coles: gde nastaje glavna probability

Za svaki kvalifikovani fixture engine skuplja istorijske fixture-e iz iste lige i prethodnih sezona.

Trening:

- samo mečevi pre decision/data cutoff-a;
- do 4 prethodne sezone prema konfiguraciji;
- najmanje 80 training mečeva;
- svaki tim mora imati najmanje 6 mečeva;
- time-decay sa istim `xi=0.0015`;
- ridge regularizacija `0.01`;
- sum-to-zero parametrizacija attack/defense strength;
- Dixon-Coles low-score korekcija `rho`.

Model daje `lambda_home` i `lambda_away`, zatim score matrix do maksimalno 10 golova po strani.

Iz score matrice se izvode:

- `P(Over 2.5)`;
- `P(Under 2.5)`;
- `P(BTTS Yes)`.

**Ovo je core model probability. H2H ne ulazi u ovaj račun.**

---

## 6. Tržište i bookmaker quote

Engine povlači odds za konkretan fixture.

`markets.py` zahteva paired quote iz istog bookmaker-a:

- target market;
- opposite market.

Podržani parovi:

- Over 2.5 / Under 2.5;
- BTTS Yes / No.

Preferirani bookmaker ID redosled je `8,11,6`, ali je `ALLOW_ANY_BOOKMAKER=true`, pa može da se koristi fallback bookmaker ako preferirani ne daje potreban market.

Za svaku stranu se računa implied probability, a zatim paired de-vig:

`p_mkt = (1/O) / ((1/O) + (1/O_opposite))`

Quote se odbacuje ako:

- nema obe strane para;
- odds < 1.45;
- overround nije između 0% i 20%.

Nema mešanja bookmaker-a u jednom market pair-u.

---

## 7. Od modela do odluke

Redosled je:

### A. Model probability

`model_probability` dolazi iz Dixon-Coles score matrice.

### B. Calibration

Ako market ima validiranu Platt kalibraciju sa najmanje 200 settled OOS observations, koristi se kalibrirana probability.

Ako nema, ostaje identity mapping i status je `IDENTITY_UNVALIDATED`.

### C. Uncertainty haircut

Od kalibrirane probability se skida 3 percentage points:

`decision_probability = max(0, calibrated_probability - 0.03)`

### D. EV

`EV = decision_probability * offered_odds - 1`

Mora biti najmanje 5%.

### E. Edge prema tržištu

`edge = decision_probability - market_devig_probability`

Mora biti najmanje 3 percentage points.

### F. Jedan market po fixture-u

Ako više marketa prođe, zadržava se market sa najvećim EV, a edge služi kao tie-break.

---

## 8. Staking

Kada je kandidat prošao model/market gates, tek tada ulazi risk engine.

Full Kelly:

`f* = (p*O - 1) / (O - 1)`

Production koristi **quarter Kelly** (`0.25 * f*`).

Dodatni limiti:

- maksimalno 1% bankroll-a po bet-u;
- maksimalno 3% novog stake-a dnevno;
- maksimalno 5% otvorenog stake-a;
- maksimalno 5 pickova dnevno;
- stake step 50 RSD;
- minimum 100 RSD;
- drawdown >=5% -> stake multiplier 0.5;
- drawdown >=10% -> nema novih pozicija.

Bitno: dnevni limit računa sve stake-ove napravljene tog dana, čak i ako je neki raniji bet već settlement-ovan.

---

## 9. Šta se zapisuje kada nastane prediction

`predictions.json` je širi audit/calibration ledger.

Za svaki modelovani market se čuva, između ostalog:

- fixture i kickoff;
- league/team IDs i imena;
- market;
- model probability;
- calibrated probability;
- calibration status;
- H2H status/rate/n/effective N/snapshot ID;
- bookmaker, odds i opposite odds;
- odds capture timestamp;
- de-vig market probability;
- overround;
- `selected` true/false;
- rejection reason;
- PENDING/settled status;
- model version.

**Ne čuvamo samo izabrani bet.** Prediction ledger služi da kasnije vidimo i šta je model video, ali nije izabrao.

---

## 10. Šta se zapisuje u `bets.json`

`bets.json` je decision ledger.

Izabrani bet dobija:

- fixture;
- market;
- signal source;
- stake;
- original odds;
- bookmaker;
- model/calibration/decision probability;
- EV/edge;
- H2H telemetry ako je dostupna;
- model version;
- status `PENDING`.

Kasnije se na isti zapis dodaju:

- closing odds;
- closing de-vig probability;
- closing capture timestamp;
- final result;
- profit;
- settlement timestamp;
- CLV odds;
- CLV probability.

Storage radi atomic file replacement, a postojeći fixture se blokira od duplog future pick-a.

---

## 11. Monitoring i closing line

`monitor.yml` trenutno radi **svakih 5 minuta**.

Monitor ima dve glavne funkcije.

### Pre-kickoff quote

Za PENDING bet u poslednja 2 sata do kickoff-a pokušava da uhvati quote kod **istog bookmaker-a** i istog marketa.

### Settlement

Kada je najmanje 90 minuta posle kickoff-a, API fixture status i rezultat određuju settlement.

Statusi:

- `FT`, `AET`, `PEN` -> završeno;
- `CANC`, `ABD` -> VOID;
- `AWD`, `WO` -> REVIEW.

Za Over/Under/BTTS rezultat se određuje iz full-time score-a.

---

## 12. T-5 closing snapshot

Postoji i poseban `capture-closing` flow.

On pokušava da uhvati quote približno 2–8 minuta pre kickoff-a, tj. cilja T-5 closing snapshot.

To je odvojeno od ranijeg 2-hour monitoring snapshot-a.

Na bet može završiti:

- `closing_5m_odd`;
- `closing_5m_opposite_odd`;
- `closing_5m_market_probability_devig`;
- `closing_5m_odds_captured_at`.

To je važnije za ozbiljan CLV research nego samo jedan raniji pre-kickoff snapshot.

---

## 13. Settlement i CLV

Za settled bet:

- WIN profit = `stake * (odd - 1)`;
- LOSS profit = `-stake`.

CLV odds:

`original_odd / closing_odd - 1`

CLV probability:

`closing_devig - original_devig`

Positive CLV znači da je tržište kasnije otišlo u smeru koji potvrđuje ranije uzetu cenu.

CLV nije isto što i profit i ne dokazuje sam po sebi profitabilnost strategije.

---

## 14. Calibration

Weekly calibration uzima samo `SETTLED` prediction rows sa binary outcome-om.

Za svaki market:

1. sortira predictions hronološki;
2. 70% koristi za fitting Platt transformacije;
3. 30% ostaje held-out validation;
4. Platt se prihvata samo ako ne pogorša ni Brier ni log-loss;
5. ECE na validation setu mora biti <=5%;
6. minimum je 200 observations po marketu;
7. validna kalibracija se onda može koristiti u engine-u.

Ako uslovi nisu ispunjeni, identity mapping ostaje aktivan i live guard ostaje konzervativan.

---

## 15. Raw API istorija

`data/raw_api/YYYY-MM-DD.jsonl` je trajni research archive uspešnih network odgovora.

Svaki zapis nosi:

- schema version;
- UTC capture timestamp;
- endpoint;
- request params;
- safe request URL bez credentials;
- request sequence number;
- GitHub workflow/run provenance kada je dostupno;
- puni API payload.

Ovo je posebno važno za debugging pitanja tipa:

> "Šta je sistem zapravo video tog jutra?"

umesto da se oslanjamo samo na konačni bet zapis.

---

## 16. H2H research istorija

H2H ima svoj append-only dataset:

`data/h2h_snapshots.jsonl`

Sadrži snapshot u trenutku odluke, uključujući kompletne H2H mečeve koji su tada bili dostupni.

`data/h2h_outcomes.jsonl`

Kasnije vezuje snapshot za konačan rezultat fixture-a.

`tools/h2h_telemetry_health.py` proverava coverage:

- predictions;
- H2H linked;
- H2H available;
- API errors;
- selected;
- selected + H2H;
- signals + H2H;
- canonical snapshots.

To je istraživački sloj koji treba da nam odgovori da li H2H zaista dodaje informaciju.

---

## 17. Health i watchdog sloj

Daily bulletin ima canonical `bulletin_health.json`.

Guard proverava da li je za današnji business date uspešno završen:

- generation;
- commit;
- send;
- completed timestamp.

Postoje i dodatni health/watchdog workflow-i za generation/settlement/bulletin tokove.

Svi state-writing workflow-i koriste concurrency grupu `quantbet-ledger` sa `cancel-in-progress: false`, kako paralelni run-ovi ne bi istovremeno menjali ledger.

---

## 18. Pages / email

Daily report se generiše iz `reporting.py`.

Email prikazuje osnovno:

- bankroll;
- ROI;
- win rate;
- drawdown;
- današnje signale;
- model probability;
- decision probability;
- EV;
- bookmaker/odds/stake.

Pages deployment objavljuje samo odabrane javne dashboard/ledger fajlove; secrets i source nisu deo javnog artifact-a.

---

## 19. Paper mode i live guard

Default je:

`PAPER_MODE=true`

Live je odbijen ako za neki od podržanih marketa nema validirane kalibracije, osim ako je eksplicitno postavljen `ALLOW_UNCALIBRATED_LIVE=true`.

To bypass ponašanje postoji samo kao guard override i nije preporuka za real staking.

---

## 20. Šta sistem NE radi

Trenutno ne radi sledeće:

- ne koristi H2H za direktno povećanje/smanjenje model probability;
- ne meša bookmaker odds u jednom paired marketu;
- ne koristi post-kickoff odds u odluci;
- ne radi in-play betting;
- ne koristi goals-in-both-halves market;
- ne tvrdi da pozitivan point ROI znači dokazanu profitabilnost;
- ne radi live staking pre validiranog OOS calibration gate-a.

---

## 21. Najvažniji fajlovi

| Fajl | Uloga |
|---|---|
| `main.py` | CLI/orchestrator |
| `src/quantbot/api.py` | API, cache, retries, raw archive |
| `src/quantbot/engine.py` | kompletan generation decision flow |
| `src/quantbot/dixon_coles.py` | core score model |
| `src/quantbot/h2h.py` | H2H filtering/weighting |
| `src/quantbot/h2h_telemetry.py` | H2H snapshot/outcome dataset |
| `src/quantbot/markets.py` | bookmaker quote pairing/de-vig |
| `src/quantbot/risk.py` | Kelly/risk/exposure |
| `src/quantbot/calibration.py` | Platt/Brier/log-loss/ECE |
| `src/quantbot/monitor.py` | closing snapshot + settlement |
| `src/quantbot/closing.py` | T-5 closing capture |
| `src/quantbot/storage.py` | atomic JSON ledger storage |
| `bets.json` | selected bet history |
| `predictions.json` | full model/prediction history |
| `data/raw_api/` | raw API evidence |
| `data/h2h_snapshots.jsonl` | H2H research evidence |
| `data/h2h_outcomes.jsonl` | H2H snapshot -> final result join |
| `calibration.json` | current calibration state |
| `ledger_meta.json` | run metadata |
| `api_usage_history.json` | API consumption history |
| `bulletin_health.json` | daily delivery health |
| `.github/workflows/` | automation |

---

## 22. Jedna mentalna mapa za svakodnevno korišćenje

Kada želiš da znaš **zašto je sistem dao bet**, idi ovim redom:

**1. Fixture** → da li je utakmica dozvoljena?

**2. Data cutoff** → šta je sistem smeo da zna u trenutku odluke?

**3. H2H** → šta je istorija direktnih duela govorila? *(research only)*

**4. Dixon-Coles** → koja je model probability?

**5. Calibration** → da li je probability validno kalibrirana?

**6. Haircut** → koliko je konzervativna decision probability?

**7. Market** → šta bookmaker trenutno nudi i koliki je de-vig fair probability?

**8. EV + edge** → da li postoji dovoljno veliki disagreement?

**9. Risk** → da li portfolio sme da uzme taj bet i koliki stake?

**10. Ledger** → šta je tačno zapisano kao dokaz odluke?

**11. Closing** → šta se kasnije desilo sa cenom?

**12. Settlement** → šta se desilo na terenu?

**13. Research** → da li model, H2H, calibration i CLV dugoročno potvrđuju priču?

Ako prođemo ovih 13 koraka, praktično možemo rekonstruisati ceo životni ciklus jednog pika.

---

## 23. Trenutne poznate dokumentacione razlike

`README.md` još uvek navodi daily schedule kao `06:00 UTC` i opisuje H2H kao obavezni selection gate. Aktuelni `daily.yml` je 00:51 Europe/Belgrade i eksplicitno uključuje H2H telemetry, dok `engine.py` koristi H2H kao telemetry, ne kao production probability input.

Zbog toga ovaj vodič namerno opisuje **stvarni runtime**, a ne staru dokumentaciju. Sledeći cleanup treba da usaglasi README i ostale stare docs sa ovim stanjem.
