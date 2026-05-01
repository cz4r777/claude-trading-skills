"""Bucket a backtest equity curve by half-year, quarter, or year and emit
per-period P/L (start, end, dollars, percent, trading days, regime tag).

Input:  JSON file containing {"equity_curve": [{"date": "...", "equity": ...}, ...], ...}
Output: stdout table + optional JSON sidecar
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def bucket_label(date_str: str, granularity: str) -> str:
    y = date_str[:4]
    m = int(date_str[5:7])
    if granularity == "year":
        return y
    if granularity == "half":
        return f"{y}-H1" if m <= 6 else f"{y}-H2"
    if granularity == "quarter":
        q = (m - 1) // 3 + 1
        return f"{y}-Q{q}"
    raise ValueError(f"unknown granularity: {granularity}")


def tag(ret_pct: float, strong: float, drawdown: float) -> str:
    if ret_pct >= strong:
        return "STRONG"
    if ret_pct <= drawdown:
        return "DRAWDOWN"
    if ret_pct < 0:
        return "loss"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="path to backtest JSON")
    ap.add_argument("--granularity", choices=["half", "quarter", "year"], default="half")
    ap.add_argument("--strong-threshold", type=float, default=25.0,
                    help="ret_pct >= this is tagged STRONG (default 25)")
    ap.add_argument("--drawdown-threshold", type=float, default=-10.0,
                    help="ret_pct <= this is tagged DRAWDOWN (default -10)")
    ap.add_argument("--equity-key", default="equity_curve",
                    help="key in the input JSON containing the equity curve list")
    ap.add_argument("--output-json", default=None,
                    help="optional output path for the structured breakdown")
    args = ap.parse_args()

    payload = json.loads(Path(args.input).read_text())
    curve = payload.get(args.equity_key) or []
    if not curve:
        print(f"ERROR: no '{args.equity_key}' in {args.input}", file=sys.stderr)
        return 1

    buckets: dict[str, list[dict]] = {}
    for row in curve:
        b = bucket_label(row["date"], args.granularity)
        buckets.setdefault(b, []).append(row)

    rows = []
    for b in sorted(buckets.keys()):
        s = buckets[b][0]["equity"]
        e = buckets[b][-1]["equity"]
        pnl = e - s
        ret_pct = (pnl / s * 100) if s else 0.0
        rows.append({
            "period":       b,
            "from":         buckets[b][0]["date"],
            "to":           buckets[b][-1]["date"],
            "start":        s,
            "end":          e,
            "pnl":          pnl,
            "ret_pct":      ret_pct,
            "trading_days": len(buckets[b]),
            "tag":          tag(ret_pct, args.strong_threshold, args.drawdown_threshold),
        })

    # Print
    label = {"half": "6-month", "quarter": "quarterly", "year": "yearly"}[args.granularity]
    print(f"backtest forensics — {label} P/L breakdown")
    print(f"{'period':<10} {'from':<11} {'to':<11} {'start':>13} {'end':>13} {'P/L $':>13} {'P/L %':>8}  days  tag")
    print("-" * 100)
    for r in rows:
        print(
            f"{r['period']:<10} {r['from']:<11} {r['to']:<11} "
            f"${r['start']:>11,.0f} ${r['end']:>11,.0f} "
            f"${r['pnl']:>+11,.0f} {r['ret_pct']:>+7.2f}%  {r['trading_days']:>4}  {r['tag']}"
        )

    start_eq = curve[0]["equity"]
    end_eq = curve[-1]["equity"]
    print("-" * 100)
    print(f"cumulative: ${start_eq:,.0f} -> ${end_eq:,.0f}  "
          f"P/L ${end_eq-start_eq:+,.0f}  {(end_eq-start_eq)/start_eq*100:+.1f}%")
    print(f"buckets:    {sum(1 for r in rows if r['ret_pct']>0)} positive / "
          f"{sum(1 for r in rows if r['ret_pct']<0)} negative / "
          f"{len(rows)} total")

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(rows, indent=2, default=str))
        print(f"\nwrote {args.output_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
