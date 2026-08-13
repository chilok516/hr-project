# HKJC Quinella Betting — Standard Operating Procedure

**Version**: 1.0
**Date**: August 2026
**Objective**: Maximize risk-adjusted returns (Sharpe ratio) through systematic HKJC quinella/quinella place betting.
**Bankroll**: $100,000 USD
**Bet Types**: 連贏 (Quinella) and 位置Q (Quinella Place)

---

## 1. Strategy Overview

### Core Principle

The system combines machine learning probability estimates (4 LightGBM models) with pari-mutuel pool analysis to identify mispriced quinella combinations. The edge comes from:
1. Fundamental model predicting horse quality better than market odds alone
2. Cold score signals detecting undervalued horses (trainer form, weight advantage, etc.)
3. EV filtering to skip -EV combos
4. Pool bias correction (β=0.855) to adjust dividend estimates

### Risk Limits

| Limit | Threshold | Action |
|-------|-----------|--------|
| Per trade | 0.5% of bankroll ($500 max/race) | Hard cap |
| Daily loss | 2% ($2,000) | Stop for rest of day |
| Weekly loss | 5% ($5,000) | Stop for rest of week + review |
| Drawdown from peak | 20% | Full system stop, manual review |
| Consecutive losses | 8 bets | Pause 1 race |
| Max daily bets | 5 races × 3 combos = 15 max | Natural limit |

---

## 2. Pre-Race Day Setup

### When
- **Sha Tin (ST)**: Sunday morning, 11:00 HKT (Race 1 at 13:00)
- **Happy Valley (HV)**: Wednesday evening, 17:00 HKT (Race 1 at 18:45 or 19:15)

### What

1. **Scrape race card**
   - Source: `racing.hkjc.com/racing/information/English/Racing/RaceCard.aspx`
   - Extract: all declared runners with horse name/number, jockey, trainer, weight, draw
   - Store in database for feature computation

2. **Run feature engineering pipeline**
   - Load historical data (34K records from 2022-2026)
   - Compute 96 features per horse: rolling form, jockey/trainer stats, pace, weight, relative-to-field, barrier, class change, incident excuses, trainer momentum
   - Output: features CSV for model inference

3. **Model retraining** (if scheduled)
   - Every 30 days: full retrain on all historical data
   - On drift detection (partial IC < 0.01): immediate retrain
   - Pre-season (August): retrain with new season data

4. **Run model inference**
   - 4 models predict: `fund_prob`, `top2_prob`, `market_prob`, `place_prob`
   - Per-race softmax normalization
   - Cold score computation using 4 calibrated signals

5. **Store predictions** in database for each horse × race combination

---

## 3. Race-Day Execution (Per Race)

### T-30 Minutes: First Odds Capture

1. Scrape live win odds from `bet.hkjc.com` via Playwright browser automation
2. Store as T1 baseline for all declared runners
3. If scrape fails: use starting price (SP) + noise as fallback, flag alert

### T-1 Minute: Second Odds Capture

1. Scrape live win odds again
2. Compute odds movement per horse:
   ```
   change% = (odds_T1 - odds_T2) / odds_T1 × 100
   ```
3. Classify:
   - Steaming (>20% drop): smart money flowing in
   - Mild steaming (10-20% drop)
   - Stable (±10%)
   - Mild drifting (10-20% rise)
   - Drifting (>20% rise): money flowing out
4. If scrape fails: use T1 odds only, apply 0.8× stake degradation

### Bet Construction

**Step 1: Rank Horses**
```
ev_score = top2_prob × log(1 + win_odds) × (1 + cold_score/10)
```
Sort descending. Take top 3 as anchors.

**Step 2: Generate Combinations**
All C(3,2) = 3 quinella combos from the 3 anchors.

**Step 3: EV Filter**
For each combo:
```
P_quinella = Harville-Stern probability
est_dividend = (1 / P_quinella × 0.75) ^ 0.855   # β-adjusted
EV = P_quinella × (est_dividend / 10)
```
Skip combo if EV < 0.4. Skip entire race if < 2 combos survive.

**Step 4: Stake Sizing**
```
cold_multiplier:
  Score 0-50th percentile:  1.0×
  Score 50-80th percentile: 1.5×
  Score 80-95th percentile: 2.0×
  Score 95th-100th:         3.0×

drift_factor (from odds movement):
  Drifting >20%:    +0.4
  Drifting 10-20%:  +0.2
  Stable:            0.0
  Steaming 10-20%:  -0.1
  Steaming >20%:    -0.3

final_stake = $100 × cold_multiplier × (1 + drift_factor)
```

**Step 5: Bet Selection**
- 連贏: All combos that pass EV filter
- 位置Q: Same combos, using place probabilities instead

**Step 6: Allocation**
- 連贏: 60% of capital
- 位置Q: 40% of capital

### Bet Submission (E3+)

1. Navigate to HKJC quinella betting page via Playwright
2. For each combo:
   - Select horse A (checkbox)
   - Select horse B (checkbox)
   - Enter stake amount
   - Click "Bet"
   - Capture confirmation page (bet reference number)
3. Time budget: 90 seconds for 3-6 combos
4. Cutoff: abort if race status shows "Going to Start"

### Race Skip Conditions

Skip the entire race if any of:
- Field size < 7 runners
- < 2 combos pass EV filter
- T1 odds scrape failed (no baseline)
- Late scratching reduced anchors to < 2
- Circuit breaker active (daily/weekly/drawdown)
- Race class/going conditions flagged (optional — system handles via EV filter)

---

## 4. Post-Race

1. **Scrape results** from HKJC `LocalResults.aspx`
   - Get finish positions for all runners
   - Get actual quinella/quinella place dividends

2. **Reconcile each bet**:
   ```
   For 連贏: did the 2 horses finish 1st and 2nd?
   For 位置Q: did both horses finish in top 3?

   If WIN: profit = (actual_dividend - 10) × (stake / 10)
   If LOSS: profit = -stake
   If VOID (late scratch): profit = 0 (refund)
   ```

3. **Update bankroll**: `bankroll += net_profit`

4. **Check circuit breakers** (in priority order):
   ```
   1. drawdown ≥ 20%?      → FULL STOP, manual review
   2. weekly loss ≥ $5K?    → Stop for rest of week
   3. daily loss ≥ $2K?     → Stop for rest of day
   4. 8 consecutive losses? → Pause 1 race
   ```

5. **Log to database**: bet outcome, actual dividend, profit, breaker status

---

## 5. End of Day

1. **Compute daily metrics**:
   - Total bets, wins, win rate
   - Total staked, total P&L, ROI
   - Per-venue breakdown (ST vs HV)
   - Per-class breakdown

2. **Update rolling 30-day metrics**:
   - Sharpe ratio (annualized)
   - ROI
   - Partial IC (model predictive power)
   - Calibration error (Brier score)

3. **Check model drift**:
   | Metric | Green | Yellow (50% stake) | Red (paper only) |
   |--------|-------|--------------------|------------------|
   | Rolling Sharpe | >0.3 | 0 to 0.3 | <0 |
   | Rolling ROI | >0% | -5% to 0% | <-5% |
   | Partial IC | >0.02 | 0.01 to 0.02 | <0.01 |
   | Brier Score | <0.15 | 0.15 to 0.25 | >0.25 |

4. **Reconcile with HKJC account statement**:
   - Match every bet reference number
   - Verify P&L for each bet
   - Flag any discrepancies (system vs statement)

5. **Send daily summary alert** (Discord/Telegram):
   ```
   🏇 HKJC Quinella — Wed 13 Aug 2026
   📊 Races: 8 | Bets: 18 | Wins: 3 (16.7%)
   💰 Staked: $2,700 | P&L: +$1,420 (ROI: +52.6%)
   📈 Bankroll: $103,240 (MTD: +3.2%)
   📉 Max DD: 4.1%
   🟢 All systems green
   ```

6. **Archive logs**: predictions, odds snapshots, bets, results

---

## 6. Race Day Schedule (Typical)

### Sha Tin (Sunday)

| Time (HKT) | Action |
|------------|--------|
| 11:00 | Pipeline start: scrape race card, run features, model inference |
| 12:00 | T1 odds capture for Race 1 begins |
| 12:29 | T2 odds capture for Race 1 (1 min before 13:00 start) |
| 12:30 | Race 1: combo construction + betting (if applicable) |
| 13:00 | Race 1 starts |
| 13:05 | Race 1 results + reconciliation |
| 13:30 | Repeat for Race 2... |
| ~18:00 | Race 10 ends |
| 18:15 | End-of-day reconciliation + report |

### Happy Valley (Wednesday)

| Time (HKT) | Action |
|------------|--------|
| 17:00 | Pipeline start |
| 18:00 | T1 odds capture begins |
| ~23:00 | Last race ends |
| 23:15 | End-of-day report |

---

## 7. Performance Benchmarks

| Metric | Green | Yellow | Red |
|--------|-------|--------|-----|
| Rolling 30d Sharpe | >0.3 | 0–0.3 | <0 |
| Rolling 30d ROI | >0% | -5%–0% | <-5% |
| Max Drawdown (since inception) | <10% | 10–15% | >15% |
| 連贏 Win Rate | >8% | 5–8% | <5% |
| 位置Q Win Rate | >20% | 15–20% | <15% |
| Avg 連贏 Dividend | >$150 | $100–150 | <$100 |
| Pipeline uptime | >95% | 85–95% | <85% |

---

## 8. Incident Response

| Incident | Response |
|----------|----------|
| Odds scrape timeout | Use T1 odds only, 0.8× stake, alert |
| Bet submission timeout | Skip race, log missed opportunity |
| HKJC website down | Wait 5 min, retry once, skip if still down |
| Model prediction error | Fall back to market odds ranking, alert |
| Database failure | Write to local backup, reconcile later |
| Incorrect bet placed | Do NOT try to cancel (risk of duplicate) — accept, log, review |
| Circuit breaker hits | Follow state machine rules, alert, log reason |
| P&L discrepancy >$50 | Flag for manual investigation |
| Playwright crash | Restart browser, resume from current race |
| Power/internet outage | Emergency stop, reconcile when back online |

---

## 9. Paper Trading → Real Money Transition

Paper trade for minimum 500 bets. All gates must pass:

| # | Gate | Threshold |
|---|------|-----------|
| 1 | Minimum bets | ≥500 |
| 2 | Sharpe ratio | ≥0.5 |
| 3 | Max drawdown | ≤15% |
| 4 | Win rate | ≥5% |
| 5 | ROI vs backtest | ±3% |
| 6 | Partial IC | ≥0.015 |
| 7 | Circuit breaker hits tested | ≥3 |

### Gradual Scale-Up

| Phase | Stake/unit | Duration | Advance if |
|-------|-----------|----------|------------|
| A | $10 (10%) | 2 weeks | All gates green |
| B | $25 (25%) | 2 weeks | Max DD < 10% |
| C | $50 (50%) | 1 month | All gates green |
| D | $100 (100%) | Ongoing | Normal operation |

---

## 10. Commands Reference

```bash
# Full pipeline (scrape → features → train → backtest)
python main.py pipeline --start 2022-09-01 --end 2026-07-31

# Walk-forward backtest only
python main.py backtest --walk-forward --min-train 10

# Train models only
python main.py train

# Predict a specific race
python main.py predict --race-date 2026/08/10 --race-no 1

# Batch scrape UK data
python scripts/batch_scrape_uk.py

# Web dashboard
python -m src.web.app       # http://localhost:8080

# Backtest report
cd src/web/static && python3 -m http.server 8088
# Open http://localhost:8088/report.html
```
