# HKJC Quinella Betting — Execution Action Plan

**Version**: 1.0
**Date**: August 2026
**Goal**: Deploy from validated backtest (+135% ROI) to live production betting
**Timeline**: ~2 weeks (part-time, 2 race days/week)

---

## Current State

| Component | Status |
|-----------|--------|
| Data pipeline (scraping) | ✅ 34K records, 296 dates, 2022-2026 |
| Feature engineering | ✅ 96 features, no leakage |
| 4-model system | ✅ AUC 0.89–0.97, date-grouped CV |
| Combo engine + EV filter | ✅ β=0.855 calibrated |
| Cold score calibration | ✅ 4 signals, LogReg weights |
| Walk-forward backtest | ✅ 連贏 +135%, 位置Q +103% |
| Circuit breakers | ✅ State machine + drift detection |
| Live odds scraper | ✅ Playwright module (needs test) |
| Web dashboard + report | ✅ FastAPI + HTML |
| HKJC betting account | 🔴 Required for Phase E3 |
| Cloud infrastructure | 🔴 Required for Phase E4 |

---

## Phase E1: Live Data Pipeline

**Goal**: Run full prediction pipeline on live race days. Zero risk — no bets placed.
**Timeline**: 2–4 race days (~1 week part-time)

### E1.1: Race Card Scraper
- **File**: `src/live/race_card.py` (new)
- **Source**: HKJC `RaceCard.aspx`
- **Output**: All declared runners with jockey, trainer, weight, draw per race
- **Validation**: Compare scraped data vs HKJC website for 1 race day

### E1.2: Feature + Model Pipeline Integration
- **File**: `src/live/pipeline.py` (new)
- **Flow**: `race card → features → models → softmax → cold score → combos → log`
- **Output**: JSON per race with selected combos, probabilities, EV, stakes
- **Validation**: Compare live predictions vs backtest logic for same races

### E1.3: Live Odds Capture Test
- **File**: `src/signals/odds_scraper.py` (modify)
- **T1 capture**: -30min before scheduled start
- **T2 capture**: -1min before scheduled start
- **Fallback**: If Playwright auth fails → use simulate mode (SP + noise)
- **Validation**: Verify odds captured match HKJC odds board within ±5%

### E1.4: Post-Race Results Reconciliation
- **File**: `src/live/reconciler.py` (new)
- **Source**: HKJC `LocalResults.aspx` (existing scraper)
- **Action**: Match predictions to actual results, compute P&L
- **Validation**: Manual check of 1 race day — all results match

### E1.5: Scheduler Setup
- **File**: `scripts/daily_pipeline.sh` (new)
- **Cron entries**:
  ```cron
  # Sha Tin Sundays
  0 11 * * 0 /path/to/scripts/daily_pipeline.sh ST
  
  # Happy Valley Wednesdays
  0 17 * * 3 /path/to/scripts/daily_pipeline.sh HV
  ```
- **Monitoring**: Check pipeline output logs for errors

### E1.6: Database Setup
- **File**: `src/live/db.py` (new)
- **Schema**: SQLite tables for predictions, odds, results, P&L
- **Tables**: `predictions`, `odds_snapshots`, `bets`, `results`, `daily_pnl`

### E1 Deliverable
Pipeline runs on 2+ live race days without errors. Predictions logged in database. Manual spot-check confirms accuracy.

---

## Phase E2: Paper Trading

**Goal**: Simulated bet logging and full performance tracking. Shadow mode — no real money.
**Timeline**: 4+ race days (~1 week)

### E2.1: Paper Bet Logger
- **File**: `src/live/paper_trader.py` (new)
- **Action**: For each combo passing EV filter, record:
  - Date, venue, race_no, horse pair, bet type, stake, T1 odds, T2 odds, EV, cold score
  - Mark as WIN/LOSS/VOID after results
- **Output**: `data/paper_trade/bets.csv`

### E2.2: Daily Performance Report
- **File**: `src/live/reporter.py` (new)
- **Output** (console + file):
  ```
  🏇 Paper Trade — Wed 13 Aug 2026
  📊 Races: 8 | Bets: 18 | Wins: 3 (16.7%)
  💰 P&L: +$1,420 (ROI: +52.6%)
  📈 Bankroll: $103,240 | Max DD: 4.1%
  🟢 All breakers: normal operation
  ```
- **Backtest comparison**: Side-by-side with expected metrics from backtest

### E2.3: Alert System
- **File**: `src/live/alerts.py` (new)
- **Channel**: Discord webhook (configurable)
- **Triggers**:
  - Race day pipeline started ✅
  - Each bet placed (race_no, combo, stake)
  - Each win/loss (race_no, combo, dividend, P&L)
  - Circuit breaker hit 🚨
  - Scrape failure ⚠️
  - Daily summary 📊

### E2.4: Dashboard Update
- **File**: `src/web/app.py` (modify)
- **Add**: Paper P&L chart, live predictions table, breaker status

### E2 Transition Gate

| Gate | Threshold | Status |
|------|-----------|--------|
| ≥500 paper bets | TBD | Track in E2 |
| Sharpe ≥ 0.5 | TBD | Track in E2 |
| Max DD ≤ 15% | TBD | Track in E2 |
| Win Rate ≥ 5% | TBD | Track in E2 |
| ROI ±3% of backtest | TBD | Track in E2 |
| Partial IC ≥ 0.015 | TBD | Track in E2 |
| ≥3 breaker hits tested | TBD | Test in E2 |

---

## Phase E3: Real Money — Micro Stakes

**Goal**: Test complete betting loop with negligible risk ($10/unit = 10% of target).
**Prerequisite**: ALL E2 transition gates passed.
**Timeline**: 2+ race days at each stake level

### E3.1: HKJC Login Automation
- **File**: `src/live/bet_submitter.py` (new)
- **Method**: Playwright browser automation
- **Flow**:
  1. Navigate to `bet.hkjc.com`
  2. Enter username/password
  3. Handle 2FA (SMS/security code — may need manual input)
  4. Verify login success
- **Security**: Credentials stored in environment variables, never in code

### E3.2: Bet Submission Flow
- **File**: `src/live/bet_submitter.py` (new)
- **Per combo**:
  1. Navigate to quinella betting page for race
  2. Select horse A checkbox + horse B checkbox
  3. Enter stake amount in input field
  4. Click "Bet" button
  5. Wait for confirmation page
  6. Extract bet reference number from confirmation HTML
  7. Log bet_ref to database
- **Timing**: 90-second budget for all combos in a race
- **Cutoff**: Abort if race status = "Going to Start"
- **No auto-retry**: Risk of duplicate bets — manual review on failure

### E3.3: Confirmation + Reconciliation
- **File**: `src/live/reconciler.py` (modify)
- **Post-race**: Check system bet_ref matches HKJC account statement
- **End of day**:
  ```
  System P&L: +$1,420
  HKJC Statement: +$1,420
  Discrepancies: 0 ✅
  ```

### E3.4: Late Scratching Detection
- **File**: `src/live/bet_submitter.py` (new)
- **Pre-bet check**: Compare declared runners vs odds board
  - Missing horse from odds board → likely scratched
  - Remove from anchor list
  - Rebuild combos with remaining anchors
  - Skip race if anchors < 2

### E3.5: Micro Stakes Deployment
- **Stake**: $10/unit (10% of target $100)
- **Caps**:
  - Max $50/race
  - Max $200/day
- **Duration**: 2 race days at $10 before scaling

### E3.6: Manual Override
- **File**: `src/live/kill_switch.py` (new)
- **Commands**:
  - `python kill_switch.py --stop` → halt all betting immediately
  - `python kill_switch.py --resume` → resume after review
  - `python kill_switch.py --status` → current breaker state
- **Emergency**: Ctrl+C to kill pipeline process

### E3 Deliverable
2+ race days at $10/unit. No missed bets. Zero reconciliation discrepancies. All breakers tested with real money.

---

## Phase E4: Full Scale

**Goal**: Scale to target stakes, activate all features.
**Prerequisite**: E3 at $10/unit for 2 weeks with all metrics green.
**Timeline**: ~2 weeks (part-time)

### E4.1: Stake Scale-Up

| Phase | Stake/unit | Max/race | Max/day | Duration |
|-------|-----------|----------|---------|----------|
| E4a | $25 (25%) | $125 | $500 | 2 weeks |
| E4b | $50 (50%) | $250 | $1,000 | 1 month |
| E4c | **$100 (100%)** | **$500** | **$2,000** | Ongoing |

Advance to next level only if all metrics green (Sharpe ≥ 0.3, Max DD ≤ 10%, Win Rate ≥ 8%).

### E4.2: Feature Activation

| Feature | Phase | Description |
|---------|-------|-------------|
| Cold score multiplier | E4a | 1×/1.5×/2×/3× stake buckets |
| Odds drift factor | E4b | Steaming/drifting interaction on stakes |
| Dynamic EV threshold | E4b | Per-race adjustment based on field size |
| 位置Q integration | E4c | Both bet types live |
| Multivariate Kelly | E4c | Covariance-aware staking |

### E4.3: Cloud Deployment
- **Platform**: AWS t3.medium or GCP e2-medium (~$35/mo)
- **Setup**:
  1. Provision VM
  2. Install Python + dependencies + Playwright
  3. Clone repository
  4. Configure cron jobs
  5. Set up PostgreSQL (migrate from SQLite)
  6. Configure monitoring (systemd service)
- **Reliability**: 24/7 uptime, auto-restart on crash

### E4.4: Weekly Auto-Retrain
- **File**: `scripts/weekly_retrain.sh` (new)
- **Schedule**: Every Monday 08:00 HKT
- **Action**: Full retrain on all historical data + last week's results
- **Validation**: Compare new model metrics vs previous, alert if degraded

### E4.5: Production Monitoring
- **Dashboard**: Real-time P&L, equity curve, breaker status, model health
- **Alerts**: Escalated to email + Discord for critical issues
- **Weekly review**: Performance summary, model performance, system health

### E4 Deliverable
Full system at target capacity. Weekly performance reviews. Continuous monitoring.

---

## Required Resources

| Resource | Phase | Detail | Estimated Cost |
|----------|-------|--------|----------------|
| HKJC betting account | E3 | Login credentials for Playwright | HKJC account required |
| Discord webhook | E2 | Alert channel | Free |
| Cloud VM | E4 | AWS t3.medium or GCP e2-medium | ~$35/month |
| Domain (optional) | E4 | For dashboard access | ~$12/year |
| Time | All | ~2 race days/week active, ~30 min/day monitoring | — |
| Bankroll | E3+ | $100,000 baseline (start at 10%) | $100K allocated |

---

## Risk Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Model overfitting | Low | High | Walk-forward backtest, date-grouped CV, paper trade validation |
| Execution failure | Medium | Medium | Circuit breakers, kill switch, reconciliation |
| Bet submission error | Medium | High | Confirmation capture, no auto-retry, daily reconciliation |
| HKJC website change | Low | Medium | Playwright selectors in config, alert on scrape failure |
| Model drift | Medium | Medium | Rolling 30d monitoring, auto-retrain triggers |
| Late scratching | Low | Low | Pre-bet detection, auto-skip if anchors < 2 |
| Network/power outage | Low | Medium | Cloud VM (E4), auto-resume on reconnect |
| Betting limit hit | Low | Low | HKJC limits ~$50K/race, we bet <$500 |

---

## Files to Create

| File | Phase | Purpose |
|------|-------|---------|
| `src/live/__init__.py` | E1 | Package init |
| `src/live/pipeline.py` | E1 | Main live pipeline orchestrator |
| `src/live/race_card.py` | E1 | Race card scraper |
| `src/live/db.py` | E1 | SQLite database layer |
| `src/live/paper_trader.py` | E2 | Paper bet logging |
| `src/live/reporter.py` | E2 | Daily performance report |
| `src/live/alerts.py` | E2 | Discord/Telegram alerts |
| `src/live/bet_submitter.py` | E3 | Playwright bet submission |
| `src/live/reconciler.py` | E3 | System vs HKJC P&L matching |
| `src/live/kill_switch.py` | E3 | Emergency stop |
| `scripts/daily_pipeline.sh` | E1 | Cron entry point |
| `scripts/weekly_retrain.sh` | E4 | Auto-retrain script |

## Files to Modify

| File | Phase | Change |
|------|-------|--------|
| `src/signals/odds_scraper.py` | E1 | Integrate with live pipeline |
| `src/web/app.py` | E2 | Add paper P&L + live predictions |
| `src/risk/breakers.py` | E3 | Production enforcement mode |

---

## Timeline Summary

| Phase | Duration | Cumulative | Risk Level |
|-------|----------|------------|------------|
| E1: Live Pipeline | 2–4 race days | 1 week | Zero (no bets) |
| E2: Paper Trading | 4–8 race days | 2 weeks | Zero (no money) |
| E3: Micro Stakes | 2 race days | 2.5 weeks | Very low ($10/unit) |
| E4: Full Scale | 2–3 weeks | 5 weeks | Moderate |
| **Total** | **~5 weeks** | | |

Race days are Wed + Sun (2/week), so 2 race days ≈ 1 calendar week.
