"""FMP-based quarterly / annual financials fetcher with rate limiting + cache.

Requires `FMP_API_KEY` env var (free tier: 250 calls/day at
https://site.financialmodelingprep.com/developer/docs).

Returns a list of dicts, one per period, with stable field names:
    period_end, period_kind, revenue, eps_basic, eps_diluted,
    net_income, gross_margin, operating_margin, ...

CLI usage:
    python fetch_fundamentals.py NVDA --quarters 8
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError as e:
    print(f"ERROR: install requests first ({e}).", file=sys.stderr)
    raise

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_cache


CATEGORY = "fundamentals"
FMP_BASE = "https://financialmodelingprep.com/api/v3"
RATE_LIMIT_S = 0.3  # 0.3s = ceiling under free-tier 250/day


def _api_key() -> Optional[str]:
    key = os.environ.get("FMP_API_KEY", "").strip()
    return key or None


def _fmp_get(path: str, params: dict | None = None) -> Optional[list | dict]:
    key = _api_key()
    if not key:
        return None
    params = dict(params or {})
    params["apikey"] = key
    url = f"{FMP_BASE}/{path.lstrip('/')}"
    try:
        time.sleep(RATE_LIMIT_S)
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 429:
            time.sleep(60)
            r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"WARN: FMP {path} failed: {e}", file=sys.stderr)
        return None


def _normalize_income(rows: list[dict], kind: str) -> list[dict]:
    """Standardize FMP income-statement payload to our stable schema."""
    out = []
    for r in rows:
        revenue = r.get("revenue")
        gross   = r.get("grossProfit")
        opinc   = r.get("operatingIncome")
        netinc  = r.get("netIncome")
        out.append({
            "period_end":  r.get("date"),
            "period_kind": kind,
            "revenue":     revenue,
            "gross_profit": gross,
            "operating_income": opinc,
            "net_income":  netinc,
            "eps_basic":   r.get("eps"),
            "eps_diluted": r.get("epsdiluted"),
            "shares_basic":   r.get("weightedAverageShsOut"),
            "shares_diluted": r.get("weightedAverageShsOutDil"),
            "gross_margin":     (gross / revenue) if revenue and gross else None,
            "operating_margin": (opinc / revenue) if revenue and opinc else None,
            "net_margin":       (netinc / revenue) if revenue and netinc else None,
        })
    return out


def fetch_quarterly_income(symbol: str, quarters: int = 8,
                           max_age_hours: float = 24.0,
                           force_refresh: bool = False) -> Optional[list[dict]]:
    """Fetch the last N quarters of income-statement data (newest first)."""
    symbol = symbol.upper()
    cache_key = f"{symbol}_quarterly_{quarters}"

    if not force_refresh:
        cached = data_cache.get_json(CATEGORY, cache_key, max_age_hours)
        if cached is not None:
            return cached

    rows = _fmp_get(f"income-statement/{symbol}",
                    {"period": "quarter", "limit": quarters})
    if not rows:
        return None
    out = _normalize_income(rows, "quarterly")
    data_cache.put_json(CATEGORY, cache_key, out)
    return out


def fetch_annual_income(symbol: str, years: int = 5,
                        max_age_hours: float = 24.0,
                        force_refresh: bool = False) -> Optional[list[dict]]:
    """Fetch the last N years of income-statement data (newest first)."""
    symbol = symbol.upper()
    cache_key = f"{symbol}_annual_{years}"

    if not force_refresh:
        cached = data_cache.get_json(CATEGORY, cache_key, max_age_hours)
        if cached is not None:
            return cached

    rows = _fmp_get(f"income-statement/{symbol}", {"limit": years})
    if not rows:
        return None
    out = _normalize_income(rows, "annual")
    data_cache.put_json(CATEGORY, cache_key, out)
    return out


def fetch_profile(symbol: str,
                  max_age_hours: float = 168.0,
                  force_refresh: bool = False) -> Optional[dict]:
    """Company profile: sector, industry, market cap, beta, etc. Slower-changing → 1-week TTL."""
    symbol = symbol.upper()
    cache_key = f"{symbol}_profile"
    if not force_refresh:
        cached = data_cache.get_json(CATEGORY, cache_key, max_age_hours)
        if cached is not None:
            return cached
    rows = _fmp_get(f"profile/{symbol}")
    if not rows:
        return None
    out = rows[0] if isinstance(rows, list) and rows else None
    if out:
        data_cache.put_json(CATEGORY, cache_key, out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("symbol")
    ap.add_argument("--quarters", type=int, default=8)
    ap.add_argument("--annual", action="store_true",
                    help="fetch annual instead of quarterly")
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--profile", action="store_true",
                    help="fetch profile (sector/industry/market cap) instead")
    ap.add_argument("--force-refresh", action="store_true")
    ap.add_argument("--output-json", default=None)
    args = ap.parse_args()

    if not _api_key():
        print("ERROR: set FMP_API_KEY env var first "
              "(free key at https://site.financialmodelingprep.com/developer/docs)",
              file=sys.stderr)
        return 1

    if args.profile:
        result = fetch_profile(args.symbol, force_refresh=args.force_refresh)
    elif args.annual:
        result = fetch_annual_income(args.symbol, args.years, force_refresh=args.force_refresh)
    else:
        result = fetch_quarterly_income(args.symbol, args.quarters,
                                        force_refresh=args.force_refresh)

    if result is None:
        print(f"FAILED: no data returned for {args.symbol}", file=sys.stderr)
        return 1

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(result, indent=2, default=str))
        print(f"wrote {args.output_json}")
    else:
        print(json.dumps(result, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
