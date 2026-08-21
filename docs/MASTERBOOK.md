# HKJC Quinella Prediction — MASTERBOOK

> **PRIVATE — credentials + API keys. Do NOT commit to public repos.**
> Read this at the start of every session (after compaction). Single source of truth for the hr-project (HK + UK horse racing).

---

## 1. Credentials & Access

### VPS (Hetzner, production)
| Field | Value |
|---|---|
| IP | `8.209.252.26` |
| SSH User | `root` |
| SSH Password | `Ncl28825569` |
| Note | password `d9UA+$mfLI%+h8@9P2` is WRONG — don't use. Connect via `paramiko` (local miniconda has it) or `sshpass`. |

### GitHub
| Field | Value |
|---|---|
| Repo | `https://github.com/chilok516/hr-project.git` |
| Local | `~/Documents/opencode-workspace/horse-racing` |

### Deploy procedure
```bash
# local: commit + push, then on VPS:
cd /opt/hr-project && git pull origin main && ./deploy.sh
# code-only change (no dockerfile/deps): 
cd /opt/hr-project && git pull && docker compose build api && docker compose up -d api
# web-only:
cd /opt/hr-project && git pull && docker compose build web && docker compose up -d web
```
Containers: `horse-racing-api` (port 8000), `horse-racing-web` (host 8321 → 3000).
`./deploy.sh` does `docker compose build` + `up -d` (rebuilds api+web).
`data/` is a Docker volume mount (`./data:/data`) — data files persist, code does NOT auto-sync (must rebuild image or `docker cp`).

---

## 2. HKJC APIs (reverse-engineered — no browser needed)

### A. Sitecore GraphQL (content + race cards) — PUBLIC, flexible
```
https://consvc.hkjc.com/content-api/JCRW/api/graph?sc_apikey={CF83F525-0B06-44FE-B643-3258BCDA089A}
```
- Arbitrary GraphQL queries allowed (no whitelist).
- Meeting/race content tree: `/sitecore/content/Sites/JCRW/Meetings/Simulcast/{season}/{meeting}/Races/{race}/`
- `Entries` field of the `Entries` folder = `Horse<TAB>Trainer` (EN names, alphabetical — NO saddlecloth).

### B. Racing data GraphQL — WHITELISTED (exact queries only)
```
https://info.cld.hkjc.com/graphql/base/   (POST JSON GraphQL)
```
- **Whitelist**: only the exact queries the SPA sends work. Modifying fields → `WHITELIST_ERROR`.
- Headers required: `Origin: https://racing.hkjc.com`, `Referer: https://racing.hkjc.com/`, browser UA.
- Working queries:
  - `SIM_getUpcomingRace($localSim: LocalSim, $oddsTypes: [OddsType])` → `commonMeetings(localSim: "SIM")` → meetings {venueCode S3/S4/S5, date, country (LIST), races [{no, postTime, raceName_en/ch, raceTrack{description_en}, ...}]}.
  - `SIM_MeetingStatus($date, $venueCode)` → `raceMeetingProfile` → races + `pmPools` (pool status).
- Full queries saved in `/tmp/hkjc_all_calls.json` (may not persist).

### C. Form Guide PDF "Starters List" (FULL race card — the accurate source)
```
https://consvc.hkjc.com/-/media/Sites/JCRW/FormGuide/Simulcast/{season}/{date}/OSE{date}_starter_{S}{r}.pdf
# e.g. season=26_27, date=20260821, S=S3, r=4  →  OSE20260821_starter_S3_r4.pdf
```
- Has: **Card (saddlecloth), Draw, Horse CN+EN, Age/Sex, Wt(lb), Rating(OR), Trainer CN+EN, Jockey CN+EN, Ref Odds**.
- Parsed with `pdfplumber` (column x-ranges are layout-specific — see `hkjc_simulcast.py`).

---

## 3. UK data source (Kaggle, free one-time)

- Dataset: `deltaromeo/horse-racing-results-ukireland-2015-2025` → `raceform.db` (SQLite, 1.1GB).
- Download: `https://www.kaggle.com/api/v1/datasets/download/deltaromeo/horse-racing-results-ukireland-2015-2025` (returns a ZIP with raceform.db + csv + PDF form guides).
- Coverage: UK/IRE 1988–2026. `type` col: Flat 1.27M / Hurdle 358K / Chase 180K / NH Flat 45K.
- Schema `data`: date, course, race_id, off, race_name, type, class, pattern, rating_band, age_band, sex_rest, dist, going, ran, num, pos, draw, ovr_btn, btn, horse, age, sex, wgt, hg, time, sp, jockey, trainer, prize, or, rpr, ts, sire, dam, damsire, owner, comment.
- **No Ex/CSF (exacta) dividend in raceform.db** — for backtest EV, Ex dividend must come from RacingPost list page or HKJC.

---

## 4. Architecture / pipeline

```
HKJC site / RacingPost / Kaggle raceform.db
   │
   ├─ scrape (HKJC simulcast / RacingPost / import raceform.db)
   │     → data/raw/uk_race_results.csv (flat UK/IRE, 478K rows)
   ├─ build_uk_features.py (feature_engine) → data/processed/uk_features.csv
   ├─ train_uk.py → data/models_uk/{fundamental,top2,market,place}_lightgbm.pkl
   └─ service.py (FastAPI) — region=hk|uk dispatch
         ├─ /predict, /races, /dates, /models/importance, /horse/form
         ├─ /live/uk/races (simulcast meetings) + /live/uk/predict (PDF starters + precomputed current-form + models)
         └─ web (Next.js BFF) → FastAPI; frontend region toggle HK/UK
```

### Key scripts (`api/scripts/`)
| Script | Purpose |
|---|---|
| `import_raceform.py` | raceform.db → uk_race_results.csv (flat UK/IRE, course→country mapping, cleaning) |
| `build_uk_features.py` | raw → uk_features.csv (feature_engine) |
| `train_uk.py` | train 4 models → models_uk/ |
| `backtest_uk.py` | UK walk-forward exacta backtest (uses SP-proxy Ex dividend) |
| `validate_uk_data.py` | UK data sanity checks |
| `batch_scrape_uk.py` | RacingPost scrape (rate-limited, mostly superseded by Kaggle) |

### Key modules (`api/src/`)
- `scraper/hkjc_simulcast.py` — HKJC simulcast: `list_meetings`, `get_race_cards`, `get_starter_runners` (PDF).
- `scraper/euro_scraper.py` — RacingPost (detail pages 406 rate-limited; list page works).
- `scraper/race_card.py` — HK synthetic race card.
- `signals/odds_poller.py` — async odds poller skeleton (UNUSED, for World Pool later).
- `models/train.py` — `HorseRaceModel` + `RacePredictor` (now supports `model_dir` for UK).

### UK live prediction (service.py `uk_live_predict`)
- Cache: `self._uk_live_cache` keyed `(meeting_code, race_no)` — re-selects instant.
- Speed: precomputed `self.uk_current_form` (latest feature row per horse, 50,986 horses) at load — avoids re-running feature_engine (~35s → ~8s first load).

---

## 5. Current state (2026-08-21)

### Done / deployed
- HK app: bilingual (zh/en), region toggle (🇭🇰 HK / 🇬🇧 UK) in header, mobile bottom nav + collapsible cards.
- UK data: 478,671 flat UK/IRE rows (2019–2026), 100% jockey/trainer/weight/draw/odds fill.
- UK models: top2 AUC 0.677, fundamental 0.551, market 0.573, place 0.561 (HK models AUC 0.89–0.97 for reference).
- UK backtest: exacta hit 22.2% per race vs 7.6% random (~3x lift). ROI INCONCLUSIVE (no real Ex dividend).
- UK live (tonight S3 York Nunthorpe day): accurate saddlecloth + CN names + jockey/trainer/weight/draw/OR + 60s auto-refresh. Verified.

### Pending / next steps
1. **World Pool odds** (EV) — not connected. Source: HKJC info.cld odds query or bet.hkjc.com (login).
2. **backtest_uk.py** — doesn't save `uk_bets_detail.json` yet (UK Backtest page needs it).
3. **UK Backtest page** — frontend region switch works, but needs uk_bets_detail.json.
4. **Chinese horse names for UK** — raceform.db is English-only; HKJC PDF gives CN names per-race (live only). Historical CN mapping = HKJC simulcast pages.
5. RacingPost detail pages (jockey/trainer/draw for historical) — rate-limited 406; Kaggle raceform.db already has full fields so RacingPost is redundant.

---

## 6. Data locations (CRITICAL — persistence)

**On VPS filesystem only (NOT in git)** — `/opt/hr-project/data/` (Docker volume):
- `raw/uk_race_results.csv` (88MB, 478K rows)
- `processed/uk_features.csv` (299MB)
- `models_uk/*.pkl` (4 × ~1.4MB)
- `raw/form_2015-present/form_2015-present/raceform.db` (766MB) + raceform.csv (718MB)

**In git** (committed): code + HK data (data/raw/race_results.csv, data/processed/features.csv, data/models/*.pkl, data/processed/names_cn.json). UK data/models NOT committed (too large).

⚠️ If the VPS `/data` volume is lost → re-download raceform.db → `import_raceform.py` → `build_uk_features.py` → `train_uk.py`. (~1h total.)

---

## 7. Gotchas / lessons learned

- **RacingPost**: full-result detail pages return `406` after ~50 requests (IP rate-limit). List page (`/results/{date}`) still works. Kaggle raceform.db is the reliable alternative.
- **HKJC info.cld**: GraphQL is whitelisted — must use the EXACT SPA query strings (saved in code comments). Don't add/remove fields.
- **HKJC starter PDF**: column x-ranges are specific (Card 24–46, Draw 130–152, Horse 153–265, Age/Sex 266–289, Wt 289–315, Rating 316–356, Trainer/Jockey split by largest x-gap 356–554, Odds 555–590). Group 1 races have rating x0=319 (3-digit) vs handicap x0=324 (2-digit) — hence the 316–356 range.
- **raceform.db `course` field**: country suffix inconsistent ("Curragh" sometimes lacks "(IRE)"). Use the `UK_COURSES`/`IRE_COURSES` sets in `import_raceform.py`, not the suffix.
- **feature_engine `rating_band`**: must stay a non-empty string (uses `.str.extract`) — import sets "0-0" placeholder.
- **Live feature matrix**: build DataFrame first, THEN set race-level metadata columns (race_date/venue/... ) — setting them on the copied current-form Series causes dtype `LossySetitemError`.
- **Machine**: local Mac often overloaded (iCloud sync, load 30+) — `tsc`/`npm build` crawl; use VPS `docker compose build web` to type-check frontend instead.

---

## 8. Quick commands (VPS)

```bash
# SSH (from local Mac, paramiko or sshpass)
sshpass -p 'Ncl28825569' ssh root@8.209.252.26

# deploy
cd /opt/hr-project && git pull && ./deploy.sh

# API logs / restart
docker logs horse-racing-api --tail 50
docker compose restart api

# test UK live prediction
curl -s 'http://localhost:8321/api/live/uk/races?date=2026-08-21'
curl -s 'http://localhost:8321/api/live/uk/predict?meeting=20260821_S3&race_no=4'

# run scripts inside container (after code rebuild)
docker exec -w /app horse-racing-api python3 scripts/build_uk_features.py
```

---

*Last updated: 2026-08-21.*
