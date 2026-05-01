---
name: backtest-forensics
description: Forensic analysis of completed backtest results. Takes an equity curve and an events log (open/close/trim records with P/L) and produces per-period P/L breakdowns (H1/H2, quarterly, yearly), win-rate-by-regime analysis, exit-reason histograms, and weak-period diagnosis. Use when a user has a backtest result and asks "why did this period underperform?", "is the model broken?", or "show me the P/L per N months".
---

# Backtest Forensics

## Overview

This skill is for **after** a backtest has been run, when the question is no longer "does this strategy work?" but "what is this strategy actually doing across regimes?"

It assumes you have two artifacts on disk:
1. An **equity curve** — a list of daily snapshots `[{"date": "YYYY-MM-DD", "equity": 12345.67, ...}, ...]`
2. An **events log** — a list of trade records `[{"date": "...", "symbol": "...", "action": "open|trim|close", "pnl": ..., "reason": "..."}, ...]`

It produces three outputs, in order of decreasing aggregation:

1. **Per-period P/L** — H1/H2 / quarterly / yearly buckets with start, end, $P/L, %P/L, trading days
2. **Regime classification** — labels each bucket as STRONG / weak / drawdown based on threshold
3. **Weak-period forensics** — for any bucket the user flags, drill into entry count, win rate, exit-reason histogram, and (if the equity curve carries gate/regime metadata) gate-on % and override fire count

## When to Use

- The user just finished a backtest and wants the first-cut performance review
- Some periods in the result look anomalously weak; need to know if it's a model bug or expected regime behavior
- The user wants P/L bucketed differently than the backtest's default (e.g. "show me 6-month chunks" instead of yearly)
- A long-window backtest needs sample-size validation (count entries / closes per regime, flag undersized cells)
- Comparing two backtest runs across the same window (e.g. a v1 vs v2 of the same strategy)

## When NOT to Use

- The user is mid-development and changing strategy rules — use [backtest-expert](../backtest-expert/) for methodology guidance first
- The user wants live-trade postmortems on individual signals — use [signal-postmortem](../signal-postmortem/)
- The user wants to test parameter sensitivity — that's a stress-test loop, this skill is for static post-hoc analysis

## Prerequisites

- Python 3.9+
- No API keys, no network calls
- Input data must be JSON / dict-shaped:
  - `equity_curve`: list of daily rows with at least `date` (ISO) and `equity` (float)
  - `events`: list of trade records with at least `date`, `action` (one of `open`/`trim`/`close`), and for `close` events a numeric `pnl`
- Optional fields on equity rows that unlock richer diagnostics:
  - `gate_inputs` (dict) or `entries_allowed` (bool) — enables gate-on/off counting
  - `regime` (string) — enables regime-tagged win-rate
- Optional fields on events that unlock richer diagnostics:
  - `reason` — exit-reason histogram
  - `entry_date` — holding-period analysis

## Workflow

### Step 1: Period bucketing

Choose a bucket size (script default: half-year = H1/H2). Bucket each equity row by its date. For each bucket compute:

```
start_eq    = first row's equity
end_eq      = last row's equity
pnl_dollars = end_eq − start_eq
ret_pct     = pnl_dollars / start_eq × 100
days        = number of equity rows in the bucket
```

Tag each bucket:
- **STRONG**: `ret_pct >= +25%`
- **DRAWDOWN**: `ret_pct <= -10%`
- **loss**: `−10% < ret_pct < 0%`
- (no tag): `0% <= ret_pct < 25%`

### Step 2: Regime detection (optional, when metadata present)

If equity rows carry `gate_inputs` or `regime`, tally per bucket:
- `gate_on_days` / `gate_off_days`
- Most-common gate `reason` (e.g. `"correction"`, `"under_pressure"`)
- Override fire count (rows with `sanity_violation == True`)

This separates "strategy was inactive" from "strategy was active but signals didn't work".

### Step 3: Trade-level forensics for flagged buckets

For each bucket the user flags as suspicious:

1. Filter `events` to rows where `lo <= date <= hi`
2. Split into opens / trims / closes
3. Compute close-event aggregates:
   - Total opens
   - Total closes (split into wins where `pnl > 0` and losses where `pnl <= 0`)
   - Win rate = wins / closes
   - Avg win = mean(positive pnls), avg loss = mean(non-positive pnls)
   - Sum of close P/L (this is the "realized" portion of the bucket's P/L; trims are unrealized partials that show up in equity but not in close P/L)
4. Reason histogram: count occurrences of each exit `reason` string

### Step 4: Diagnosis output

Render a structured report. Each suspicious bucket gets a panel:

```
================================================================
2023-H2   2023-07-03 -> 2023-12-29   +2.06%   $+3,527
================================================================
  trading days     126
  gate ON          121 (96.0%)
  gate OFF         5
  sanity violations 20
  gate paths       {'primary_open': 101, 'override_fired': 20, 'blocked': 5}
  top gate reasons [('confirmed_uptrend', 101), ('override(under_pressure)', 20), ...]
  ----
  trades opened    32
  closes           34   (wins 8 / losses 26)
  trims            8
  close P/L sum    $-13,655
  avg win / loss   $+4,040 / $-1,768
  close reasons    {'stock_<50dma': 12, 'max_loss': 8, 'stock_stop': 4, ...}
  trim reasons     {'profit_take_2x': 8}
```

The user can read this and answer "model broken or working as designed?" by looking at:
- **High gate-on % + low win rate + small avg loss + many `max_loss` exits** → working as designed in chop. Strategy entered breakouts, they failed, loss control worked.
- **High gate-off % + low entry count** → working as designed in correction. Gate did its job blocking entries.
- **High win rate + high avg loss + few trims** → suspicious. Possible bug in profit-take or trim logic.
- **Zero entries with gate-on >0%** → suspicious. Possible bug in entry filtering (Stage 2 gate, breakout detector, etc.).

### Step 5: Comparison row (optional)

If the user supplies a reference period (e.g. a strong half), include it in the same panel format. Direct visual comparison shows what the same gate / same setup looks like in a regime where signals worked.

## Key Interpretation Principles

### Win-rate flexes with regime

A breakout-style strategy will show **15-25% win rate in chop** and **45-55% win rate in trends** — the difference is regime, not bug. Don't expect uniform win rates across periods.

### Loss control is the constant

Average loss per trade as a % of equity should stay roughly constant across periods (e.g. ~1% per trade). If it doesn't, the position-sizer is broken — that IS a bug.

### Trims subsidize chop halves

Look for partial profit-takes (`trim` events with reasons like `profit_take_2x`). In chop halves, trims often keep a half barely positive when close P/L is negative. That's the asymmetric expectancy of "many small losses, fewer larger winners" working.

### Sample size matters per bucket

A half with 5 entries and a 20% win rate is statistically uninformative — could be noise. Flag any bucket with `entries < 10` as low-confidence.

## Output

By default the script writes:
- `reports/forensics_<timestamp>.json` — full structured report (all buckets + flagged-period drill-downs)
- `reports/forensics_<timestamp>.md` — human-readable report

Custom output paths via `--output-dir`.

## Resources

- `scripts/period_breakdown.py` — bucket the equity curve by H1/H2, quarter, or year
- `scripts/diagnose_period.py` — drill-down forensics on flagged buckets
- `scripts/forensics_report.py` — combined wrapper that produces both outputs
- `references/methodology.md` — how to interpret each metric and the "broken vs working as designed" decision tree
- `references/event_schema.md` — exact field names and types expected on equity_curve and events

## Critical Reminders

**This skill assumes the backtest already ran cleanly.** It does not validate the engine, slippage model, or signal generation — those are the job of [backtest-expert](../backtest-expert/) before this skill ever runs.

**Trims are not closes.** Some backtest engines emit `trim` events for partial profit-takes (e.g. sell half at +50%); these add to equity but are not "closed" round trips. Compute close-only metrics on `action == "close"` events; equity-curve-based P/L includes trims automatically.

**Don't extrapolate from undersized buckets.** If a half has fewer than 10 entries, the win-rate and avg-win/loss numbers are noise. Note the sample size, don't draw conclusions.
