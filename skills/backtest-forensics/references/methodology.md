# Forensic Interpretation Methodology

This document is the decision tree for "model broken vs working as designed" when diagnosing weak periods in a backtest.

## The asymmetric expectancy worldview

Most non-trivial trading strategies — especially momentum / breakout / trend-following — are **asymmetric**: they take many small losses and a few large winners. This shows up as:

- Overall win rate: 25–40%
- Avg win / avg loss ratio: 2.5–4×
- Per-period win rate: highly variable (15% in chop, 50%+ in trends)

**Do not expect uniform performance.** A half with a 15% win rate is not automatically broken.

## Decision tree for a flagged weak period

For each weak period, check these signals in order:

### 1. Was the strategy active?

If `gate_on_days / trading_days < 50%` → the strategy was *correctly inactive* due to its market filter (regime / DD counter / etc.). The flat performance is the gate doing its job. **Not a bug.**

If `gate_on_days / trading_days >= 80%` → the strategy was active. Continue to (2).

### 2. Did entries fire?

If `entries == 0` despite high gate-on % → bug suspected. The setup filter (Stage 2 trend template, breakout detector, etc.) rejected every candidate. Verify by spot-checking on a known-good day from a strong period; if the same logic still produces zero entries, the data feed is the suspect.

If `entries >= 5` and `closes >= 5` → continue to (3).

If `0 < entries < 5` → low-confidence sample. Don't draw conclusions; widen the period or accept the noise.

### 3. Did entries succeed at the typical rate?

If `win_rate >= 35%` and `avg_win/avg_loss >= 2.5` and bucket P/L is still flat or slightly negative → the **trim mechanic** likely subsidized the bucket. Check `trim` event count; if trims > closes/2, that's the working-as-designed pattern.

If `win_rate < 25%` and the period was a known choppy market regime → **working as designed**. Breakouts triggered, trends didn't follow through, loss control kicked in. Verify by checking exit reasons (4).

If `win_rate >= 35%` but P/L is still negative → suspicious. The asymmetry isn't working. Check (5).

### 4. Are exit reasons consistent with the regime story?

For a chop regime where breakouts fail, expect exit reasons dominated by:
- `max_loss` / `premium_decay` (option premium hit zero)
- `stock_<50dma` / `signal_invalidated` (technical exit on signal failure)
- `stock_stop` / `hard_stop` (price-based stop)

If those dominate, the strategy executed its losses correctly. **Not a bug.**

For a trending regime where breakouts work, expect:
- `profit_take_3x` / `target_hit` (winner ran)
- `trailing_stop` / `peak_drawdown` (winner ended on a pullback after running)
- A material count of `trim` events with `profit_take_2x` reasons

If a flagged period is mostly the chop pattern, it correctly handled chop. Don't conflate "low return" with "broken".

### 5. Position sizing as the constancy check

Across all periods (including flagged ones), `avg_loss / start_equity` should be roughly constant. For a strategy with a 1% risk-per-trade target:

| Period equity | Expected avg loss | Tolerance |
|--------------|-------------------|-----------|
| $100k        | -$1,000           | ±50%      |
| $500k        | -$5,000           | ±50%      |
| $5M          | -$50,000          | ±50%      |

If this constancy breaks, the position-sizer is broken — **that IS a bug**, regardless of headline returns. Investigate `allocation/` or whatever module computes position size.

## Common false alarms (not bugs)

- **A flat half after a strong half.** This is mean reversion in regime, not strategy failure. Trends don't compound forever; the bot rests during chop.
- **A negative half during a known bear (2018, 2020 COVID, 2022).** Long-only momentum strategies *should* lose money in bears. Check that the loss is bounded by your max-DD ceiling; that's the safety constraint working.
- **Lower win rate at higher equity.** As capital grows, position size grows; same percentage moves produce bigger absolute swings. Use `pnl_dollars / start_eq` not raw dollars to compare across time.
- **Many `max_loss` exits in a chop period.** Long-call strategies see total premium decay on failed breakouts. That's bounded loss, not a glitch.

## Red flags (real bugs)

- `entries == 0` with gate ON and known good market days in the period → entry filter bug
- `avg_loss / start_equity` drifting (e.g. 0.5% in early periods, 3% in later periods) → position sizer drift, possibly equity calculation bug
- `wins > losses` but P/L sum is negative → P/L attribution bug or fee miscalculation
- `closes` count doesn't match `opens − still_open` → events accounting bug
- A period with `sanity_violation` count > `gate_off_days` → override is firing more than the underlying gate is blocking; check override conditions

## Sample size guard

| Closes in bucket | Statistical confidence |
|------------------|------------------------|
| < 5              | None — quote with a "low sample" warning |
| 5–10             | Directional only — don't compute precise win rate |
| 10–30            | Moderate — 95% CI is wide |
| 30+              | High — standard inference applies |

Apply the same guard to the full backtest's total close count — the [backtest-expert](../../backtest-expert/) skill recommends 100+ for high confidence.

## When the answer is "the model is working but the regime was bad"

Sometimes the honest answer is: the strategy is correct, the period was a bad fit. In that case, the right output is *not* "fix the bug" but "document the regime sensitivity":

1. Tag the bucket with its regime label (chop / correction / trending / mega-trend)
2. Compute regime-conditional expectancy (per-trade return given the regime)
3. Surface the "% of years in unfavorable regime" — that's the floor of how often the strategy underperforms
4. Compare to a buy-and-hold benchmark in the same period — if the strategy lost less than buy-and-hold, that's still alpha

The user can then decide: tolerate the regime-sensitivity, or build a regime-specific overlay (which is a different strategy, not a bug fix).
