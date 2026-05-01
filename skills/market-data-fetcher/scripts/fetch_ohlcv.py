"""yfinance-based OHLCV fetcher with disk cache.

Returns a pandas DataFrame indexed by date with lowercase columns:
    open, high, low, close, adj_close, volume

CLI usage:
    python fetch_ohlcv.py AAPL --lookback-days 1500 --output-csv aapl.csv
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f"ERROR: install dependencies first ({e}). pip install pandas yfinance", file=sys.stderr)
    raise

# Allow running as a script — add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_cache


CATEGORY = "ohlcv"


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename yfinance's CamelCase to lowercase snake; standardize Adj Close → adj_close."""
    rename = {
        "Open": "open", "High": "high", "Low": "low", "Close": "close",
        "Adj Close": "adj_close", "Volume": "volume",
    }
    df = df.rename(columns=rename)
    keep = [c for c in ["open", "high", "low", "close", "adj_close", "volume"] if c in df.columns]
    df = df[keep]
    df.index.name = "date"
    return df


def fetch_ohlcv(
    symbol: str,
    lookback_days: int = 1000,
    max_age_hours: float = 24.0,
    auto_adjust: bool = True,
    force_refresh: bool = False,
    retries: int = 2,
) -> Optional[pd.DataFrame]:
    """Fetch OHLCV for a symbol.

    Returns a DataFrame indexed by date with lowercase columns, or None on failure.
    """
    symbol = symbol.upper()

    # Cache hit?
    if not force_refresh:
        cached = data_cache.get_df(CATEGORY, symbol, max_age_hours)
        if cached is not None and len(cached) >= lookback_days:
            return cached.tail(lookback_days)

    # Fetch from yfinance
    period = f"{int(lookback_days * 1.5 / 252) + 1}y"  # add margin for non-trading days
    last_err = None
    for attempt in range(retries + 1):
        try:
            df = yf.Ticker(symbol).history(period=period, auto_adjust=auto_adjust)
            if df is None or len(df) == 0:
                last_err = "empty response"
                if attempt < retries:
                    time.sleep(1.0 + attempt)
                    continue
                return None
            df = _normalize_columns(df)
            data_cache.put_df(CATEGORY, symbol, df)
            return df.tail(lookback_days)
        except Exception as e:
            last_err = str(e)
            if attempt < retries:
                time.sleep(1.0 + attempt * 2)
                continue

    print(f"WARN: fetch_ohlcv({symbol}) failed: {last_err}", file=sys.stderr)
    return None


def fast_info(symbol: str) -> dict:
    """Lightweight quote dict — last_price, previous_close, change_pct."""
    try:
        info = yf.Ticker(symbol).fast_info
        last = float(info.last_price)
        prev = float(info.previous_close)
        return {
            "symbol": symbol.upper(),
            "last_price": round(last, 4),
            "previous_close": round(prev, 4),
            "change_pct": round((last - prev) / prev * 100, 2) if prev else 0.0,
        }
    except Exception as e:
        return {"symbol": symbol.upper(), "error": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("symbols", nargs="+", help="one or more ticker symbols")
    ap.add_argument("--lookback-days", type=int, default=1000)
    ap.add_argument("--max-age-hours", type=float, default=24.0)
    ap.add_argument("--no-auto-adjust", action="store_true",
                    help="return raw prices (default: auto-adjusted for splits/divs)")
    ap.add_argument("--force-refresh", action="store_true")
    ap.add_argument("--output-csv", default=None,
                    help="if single symbol, write CSV to this path; multi-symbol writes a dir")
    args = ap.parse_args()

    results = {}
    for sym in args.symbols:
        df = fetch_ohlcv(
            sym, args.lookback_days, args.max_age_hours,
            auto_adjust=not args.no_auto_adjust,
            force_refresh=args.force_refresh,
        )
        if df is None:
            print(f"  {sym}: FAILED")
        else:
            print(f"  {sym}: {len(df)} rows ({df.index[0].date()} -> {df.index[-1].date()})")
            results[sym] = df

    if args.output_csv and results:
        out = Path(args.output_csv)
        if len(results) == 1:
            list(results.values())[0].to_csv(out)
            print(f"wrote {out}")
        else:
            out.mkdir(parents=True, exist_ok=True)
            for sym, df in results.items():
                df.to_csv(out / f"{sym}.csv")
            print(f"wrote {len(results)} files to {out}/")

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
