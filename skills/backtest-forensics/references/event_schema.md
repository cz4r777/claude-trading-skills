# Backtest input schema

The forensics scripts read a JSON file with two top-level lists. The exact schema is loose by design — only a few fields are required, the rest unlock optional features.

## Top-level shape

```json
{
  "equity_curve": [ {row}, {row}, ... ],
  "events":       [ {event}, {event}, ... ],
  "stats":        { ... }     // ignored by forensics scripts
}
```

The `equity_curve` and `events` keys are configurable via `--equity-key` and `--events-key` if your engine uses different names.

## equity_curve row schema

Required:

| field   | type   | notes |
|---------|--------|-------|
| `date`  | string | ISO `YYYY-MM-DD` |
| `equity`| number | total portfolio equity at end of day |

Optional — these unlock richer reporting:

| field             | type   | unlocks |
|-------------------|--------|---------|
| `entries_allowed` | bool   | gate-on/off counts |
| `gate_inputs`     | dict   | gate-reason histogram, override count, gate-path tally |
| `gate_inputs.allow_entries` | bool | gate-on/off (preferred over `entries_allowed`) |
| `gate_inputs.reason`        | string | what the gate said ("confirmed_uptrend", "correction", etc.) |
| `gate_inputs.path`          | string | which decision branch ("primary_open", "blocked", "override_fired") |
| `gate_inputs.sanity_violation` | bool | override fired against the primary gate decision |
| `regime`          | string | regime classification (e.g. "bull", "neutral", "bear") |
| `cash`            | number | cash component of equity |
| `mtm`             | number | mark-to-market component (open positions) |
| `open_positions`  | int    | number of open positions |

## events row schema

Required:

| field    | type   | notes |
|----------|--------|-------|
| `date`   | string | ISO `YYYY-MM-DD` |
| `action` | string | one of: `"open"`, `"trim"`, `"close"` |

Required for `action == "close"`:

| field  | type   | notes |
|--------|--------|-------|
| `pnl`  | number | realized P/L in dollars (positive = win) |

Optional but very useful:

| field           | type   | unlocks |
|-----------------|--------|---------|
| `symbol`        | string | per-symbol breakdowns |
| `reason`        | string | exit-reason histogram (use stable strings, not free-form) |
| `entry_date`    | string | holding-period analysis |
| `entry_price`   | number | move-to-stop / win-distance analysis |
| `peak_price`    | number | "did this trade leave money on the table" analysis |
| `shares` / `contracts` | number | size attribution |
| `layer`         | string | which pyramid layer was traded ("pilot", "half", "full") |

## What if my engine doesn't emit `trim` events?

That's fine. The forensics scripts treat trims as a separate event class — if you don't have them, `trims = 0` and the report omits the trim section. Closes alone are sufficient for the win-rate / avg-win / avg-loss / exit-reason analysis.

## What if my engine doesn't emit `gate_inputs`?

Also fine. Without gate metadata, the diagnostic skips the gate-on/off section and goes straight to trade-level forensics. You'll lose the ability to distinguish "strategy was correctly inactive" from "strategy was active but signals failed", but everything else still works.

## Adding the schema to your engine

The minimal change to make a backtest engine forensics-compatible:

```python
# at end of each replay day:
result.equity_curve.append({
    "date":   date_str,
    "equity": current_total_equity,
})

# at every trade-close:
result.events.append({
    "date":   date_str,
    "action": "close",
    "symbol": sym,
    "pnl":    realized_pnl_dollars,
    "reason": exit_reason_string,    # encourage a stable enum
})

# at every partial profit-take:
result.events.append({
    "date":   date_str,
    "action": "trim",
    "symbol": sym,
    "reason": "profit_take_2x",       # or whatever your trim trigger is
})

# at every position open:
result.events.append({
    "date":   date_str,
    "action": "open",
    "symbol": sym,
})
```

That's it. With those four fields per event and `date` + `equity` per equity-curve row, the forensics scripts work end-to-end.

## Encouraging stable exit-reason strings

The exit-reason histogram is only useful if reason strings are reused across trades. Encourage a small enum like:

| Reason | When |
|--------|------|
| `max_loss` | premium decayed to floor (option strategies) |
| `stock_stop` | hard price stop hit |
| `stock_<50dma` | signal-based technical exit |
| `expiry_near` | option approaching expiry |
| `profit_take_2x` | first trim at 2× premium |
| `profit_take_3x` | full close at 3× premium |
| `trailing_stop` | trailing-stop triggered |
| `time_stop` | held for max-allowed days |

Free-form strings like `"sold because RSI was 78.3 on bar 47"` are still accepted, but the histogram won't aggregate them — each unique string becomes its own bucket.
