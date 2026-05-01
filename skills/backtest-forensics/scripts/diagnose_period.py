"""Drill-down forensics on one or more flagged periods inside a backtest.

For each period (date range), report: trading days, gate-on/off counts (if
metadata present), entry count, close win/loss split, exit-reason histogram,
and dollar P/L. Useful for answering "why did this period underperform?"

Input:  JSON file with {"equity_curve": [...], "events": [...]}
Output: human-readable panels + optional JSON sidecar
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def parse_periods(spec: list[str]) -> list[tuple[str, str, str]]:
    """Parse strings like '2023-H2:2023-07-01:2023-12-31' into (label, lo, hi)."""
    out = []
    for s in spec:
        parts = s.split(":")
        if len(parts) != 3:
            raise ValueError(f"period spec must be 'LABEL:YYYY-MM-DD:YYYY-MM-DD', got {s}")
        out.append((parts[0], parts[1], parts[2]))
    return out


def in_period(date_str: str, lo: str, hi: str) -> bool:
    return lo <= date_str <= hi


def diagnose(curve, events, label, lo, hi):
    rows = [r for r in curve if in_period(r["date"], lo, hi)]
    if not rows:
        return None
    evs = [e for e in events if in_period(e["date"], lo, hi)]

    days = len(rows)

    # Gate metadata is optional — fall back gracefully
    on_days = 0
    off_days = 0
    sanity_violations = 0
    reason_counts = Counter()
    path_counts = Counter()
    has_gate_meta = False
    for r in rows:
        gi = r.get("gate_inputs") or {}
        ea = r.get("entries_allowed")
        if gi or ea is not None:
            has_gate_meta = True
        allowed = gi.get("allow_entries") if gi else ea
        if allowed:
            on_days += 1
        elif allowed is False:
            off_days += 1
        if gi.get("sanity_violation"):
            sanity_violations += 1
        if gi.get("reason"):
            reason_counts[gi["reason"]] += 1
        if gi.get("path"):
            path_counts[gi["path"]] += 1

    opens  = [e for e in evs if e.get("action") == "open"]
    closes = [e for e in evs if e.get("action") == "close"]
    trims  = [e for e in evs if e.get("action") == "trim"]

    close_pnl = [e.get("pnl", 0) or 0 for e in closes]
    wins   = [p for p in close_pnl if p > 0]
    losses = [p for p in close_pnl if p <= 0]

    close_reasons = Counter(e.get("reason", "?") for e in closes)
    trim_reasons  = Counter(e.get("reason", "?") for e in trims)

    start_eq = rows[0]["equity"]
    end_eq = rows[-1]["equity"]
    pnl_dollars = end_eq - start_eq
    ret_pct = (pnl_dollars / start_eq * 100) if start_eq else 0

    win_rate = (len(wins) / len(closes) * 100) if closes else 0.0
    avg_loss_pct_eq = (
        (sum(losses) / len(losses) / start_eq * 100) if losses and start_eq else 0.0
    )

    return {
        "label":           label,
        "from":            rows[0]["date"],
        "to":              rows[-1]["date"],
        "trading_days":    days,
        "has_gate_meta":   has_gate_meta,
        "gate_on_days":    on_days,
        "gate_off_days":   off_days,
        "gate_on_pct":     round(on_days / days * 100, 1) if days else 0,
        "sanity_violations": sanity_violations,
        "gate_reason_top": reason_counts.most_common(5),
        "gate_path":       dict(path_counts),
        "opens":           len(opens),
        "closes":          len(closes),
        "trims":           len(trims),
        "close_wins":      len(wins),
        "close_losses":    len(losses),
        "win_rate":        round(win_rate, 1),
        "close_pnl_sum":   round(sum(close_pnl), 0),
        "avg_win":         round(sum(wins) / len(wins), 0) if wins else 0,
        "avg_loss":        round(sum(losses) / len(losses), 0) if losses else 0,
        "avg_loss_pct_eq": round(avg_loss_pct_eq, 2),
        "close_reasons":   dict(close_reasons),
        "trim_reasons":    dict(trim_reasons),
        "start_eq":        start_eq,
        "end_eq":          end_eq,
        "pnl_dollars":     round(pnl_dollars, 0),
        "ret_pct":         round(ret_pct, 2),
    }


def print_report(reports):
    for r in reports:
        if r is None:
            continue
        print(f"\n{'='*88}")
        print(f"{r['label']}   {r['from']} -> {r['to']}   "
              f"{r['ret_pct']:+.2f}%   ${r['pnl_dollars']:+,.0f}")
        print('='*88)
        print(f"  trading days     {r['trading_days']}")
        if r["has_gate_meta"]:
            print(f"  gate ON          {r['gate_on_days']:>4} ({r['gate_on_pct']}%)")
            print(f"  gate OFF         {r['gate_off_days']:>4}")
            print(f"  sanity violations {r['sanity_violations']}")
            if r["gate_path"]:
                print(f"  gate paths       {r['gate_path']}")
            if r["gate_reason_top"]:
                print(f"  top gate reasons {r['gate_reason_top']}")
            print(f"  ----")
        print(f"  trades opened    {r['opens']}")
        print(f"  closes           {r['closes']}  (wins {r['close_wins']} / losses {r['close_losses']})")
        print(f"  trims            {r['trims']}")
        print(f"  win rate         {r['win_rate']}%")
        print(f"  close P/L sum    ${r['close_pnl_sum']:+,.0f}")
        print(f"  avg win / loss   ${r['avg_win']:+,.0f} / ${r['avg_loss']:+,.0f}")
        print(f"  avg loss / eq    {r['avg_loss_pct_eq']}%")
        if r["close_reasons"]:
            top_close = sorted(r["close_reasons"].items(), key=lambda x: -x[1])[:8]
            print(f"  close reasons    {dict(top_close)}")
        if r["trim_reasons"]:
            top_trim = sorted(r["trim_reasons"].items(), key=lambda x: -x[1])[:8]
            print(f"  trim reasons     {dict(top_trim)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="path to backtest JSON")
    ap.add_argument("--period", action="append", required=True,
                    help="period spec 'LABEL:YYYY-MM-DD:YYYY-MM-DD' (repeat for multiple)")
    ap.add_argument("--equity-key", default="equity_curve")
    ap.add_argument("--events-key", default="events")
    ap.add_argument("--output-json", default=None)
    args = ap.parse_args()

    payload = json.loads(Path(args.input).read_text())
    curve  = payload.get(args.equity_key) or []
    events = payload.get(args.events_key) or []
    if not curve:
        print(f"ERROR: no '{args.equity_key}' in {args.input}", file=sys.stderr)
        return 1

    periods = parse_periods(args.period)
    reports = [diagnose(curve, events, lbl, lo, hi) for lbl, lo, hi in periods]
    print_report(reports)

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(reports, indent=2, default=str))
        print(f"\nwrote {args.output_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
