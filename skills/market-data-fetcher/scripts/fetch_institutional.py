"""Institutional ownership fetcher.

Tries FMP first (holder count + sharesOutstanding for ownership %), falls
back to Finviz scraping when FMP doesn't have shares-outstanding data.

CLI usage:
    python fetch_institutional.py AAPL MSFT NVDA --output-json holders.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"ERROR: install requests + beautifulsoup4 first ({e}).", file=sys.stderr)
    raise

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_cache


CATEGORY = "institutional"
FMP_BASE = "https://financialmodelingprep.com/api/v3"
FMP_RATE_LIMIT_S = 0.3
FINVIZ_RATE_LIMIT_S = 2.0
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
]


def _fmp_key() -> Optional[str]:
    k = os.environ.get("FMP_API_KEY", "").strip()
    return k or None


def _fmp_get(path: str, params: dict | None = None):
    key = _fmp_key()
    if not key:
        return None
    p = dict(params or {})
    p["apikey"] = key
    try:
        time.sleep(FMP_RATE_LIMIT_S)
        r = requests.get(f"{FMP_BASE}/{path.lstrip('/')}", params=p, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _from_fmp(symbol: str) -> Optional[dict]:
    """Get holder count + ownership % via FMP. Needs both holder list and sharesOutstanding."""
    holders = _fmp_get(f"institutional-holder/{symbol}")
    if not holders:
        return None

    quote = _fmp_get(f"quote/{symbol}")
    shares_out = None
    if isinstance(quote, list) and quote:
        shares_out = quote[0].get("sharesOutstanding")

    total_shares_held = sum((h.get("shares") or 0) for h in holders)
    ownership_pct = (
        (total_shares_held / shares_out * 100) if shares_out else None
    )

    return {
        "symbol": symbol.upper(),
        "source": "fmp",
        "holder_count": len(holders),
        "shares_held": total_shares_held,
        "shares_outstanding": shares_out,
        "ownership_pct": round(ownership_pct, 2) if ownership_pct is not None else None,
        "as_of": time.strftime("%Y-%m-%d"),
    }


def _from_finviz(symbol: str) -> Optional[dict]:
    """Scrape Finviz for institutional ownership %. Free, no key, 2s rate-limited."""
    import random
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    url = f"https://finviz.com/quote.ashx?t={symbol}"
    try:
        time.sleep(FINVIZ_RATE_LIMIT_S)
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        # The snapshot table has a "Inst Own" cell; value is in the next td as "XX.XX%"
        cells = soup.select("table.snapshot-table2 td")
        for i, c in enumerate(cells):
            if c.get_text(strip=True) == "Inst Own" and i + 1 < len(cells):
                val = cells[i + 1].get_text(strip=True)
                m = re.match(r"^([\d.]+)%$", val)
                if m:
                    return {
                        "symbol": symbol.upper(),
                        "source": "finviz",
                        "holder_count": None,
                        "shares_held": None,
                        "shares_outstanding": None,
                        "ownership_pct": float(m.group(1)),
                        "as_of": time.strftime("%Y-%m-%d"),
                    }
        return None
    except Exception:
        return None


def fetch_institutional_ownership(
    symbol: str,
    max_age_hours: float = 168.0,  # institutional data updates quarterly; 1-week TTL
    force_refresh: bool = False,
    prefer: str = "fmp",  # "fmp" or "finviz"
) -> Optional[dict]:
    """Fetch institutional holder data, FMP-first with Finviz fallback (or vice versa)."""
    symbol = symbol.upper()

    if not force_refresh:
        cached = data_cache.get_json(CATEGORY, symbol, max_age_hours)
        if cached is not None:
            return cached

    primary, fallback = (_from_fmp, _from_finviz) if prefer == "fmp" else (_from_finviz, _from_fmp)
    result = primary(symbol)
    # FMP without sharesOutstanding → fall back to Finviz for ownership_pct
    if result and result.get("ownership_pct") is None:
        finviz = _from_finviz(symbol)
        if finviz and finviz.get("ownership_pct"):
            result["ownership_pct"] = finviz["ownership_pct"]
            result["source"] = "fmp+finviz"
    if result is None:
        result = fallback(symbol)

    if result:
        data_cache.put_json(CATEGORY, symbol, result)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--prefer", choices=["fmp", "finviz"], default="fmp")
    ap.add_argument("--force-refresh", action="store_true")
    ap.add_argument("--output-json", default=None)
    args = ap.parse_args()

    out = {}
    for sym in args.symbols:
        r = fetch_institutional_ownership(sym, prefer=args.prefer,
                                           force_refresh=args.force_refresh)
        if r is None:
            print(f"  {sym}: FAILED")
        else:
            print(f"  {sym}: {r['source']}, {r.get('ownership_pct', '?')}% "
                  f"({r.get('holder_count', '?')} holders)")
            out[sym] = r

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(out, indent=2, default=str))
        print(f"wrote {args.output_json}")

    return 0 if out else 1


if __name__ == "__main__":
    raise SystemExit(main())
