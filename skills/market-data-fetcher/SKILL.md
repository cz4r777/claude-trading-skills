---
name: market-data-fetcher
description: Unified market data fetcher across yfinance (OHLCV), FMP (fundamentals + institutional holders), and Finviz (institutional ownership %, news). Provides a single API with disk caching, rate-limit awareness, and source-fallback chains. Use when a user needs historical OHLCV, quarterly/annual financials, EPS history, institutional ownership, or sector-classification data and doesn't want to manage three different rate limiters and response shapes.
---

# Market Data Fetcher

## Overview

This skill is the data plumbing layer for trading / backtesting workflows. It wraps three free or freemium sources behind one interface:

- **yfinance** (free, no key) — OHLCV, dividends, splits, fast-info quotes
- **Financial Modeling Prep (FMP)** (free tier 250 calls/day, paid tiers higher) — quarterly/annual financials, institutional holders, profile, key metrics
- **Finviz** (free, web scraping) — institutional ownership %, news headlines, screener results

Each fetcher returns a stable shape (pandas DataFrame for time series, dict for snapshots), caches results to disk, and respects rate limits.

The point is **not** to add new data sources — the point is to remove the boilerplate of "yfinance failed for this ticker, fall back to FMP, oh wait FMP is rate-limited, sleep and retry".

## When to Use

- A backtest or screener needs OHLCV for many tickers and the user doesn't want to write the cache layer
- Fundamentals (EPS, revenue, margin) are needed for a CANSLIM-style screen and the user wants the FMP integration without writing the rate limiter
- Institutional ownership data is needed and FMP's `sharesOutstanding` field is missing — Finviz fallback should kick in automatically
- A skill (e.g. [canslim-screener](../canslim-screener/), [vcp-screener](../vcp-screener/), [pead-screener](../pead-screener/)) needs data and the user wants a single dependency rather than three

## When NOT to Use

- Real-time quotes for live trading — this skill is for historical / EOD data, not low-latency feeds. Use a broker SDK (Alpaca, IBKR) for live.
- Options chain data — yfinance returns *current* chains only and FMP doesn't have historical chains. Use a paid feed (CBOE DataShop, ORATS, Polygon options) for that.
- News sentiment / NLP — Finviz scraper here returns headlines as strings only, no scoring.

## Prerequisites

- Python 3.9+
- Required: `pandas`, `requests`, `yfinance`, `beautifulsoup4`, `lxml`
- Optional: `pyarrow` (for parquet cache; falls back to JSON if absent)
- Optional API key: `FMP_API_KEY` env var — without it, FMP fetchers return `None` and the fallback chain skips to the next source

```bash
pip install pandas requests yfinance beautifulsoup4 lxml pyarrow
```

## Workflow

### Step 1: Choose the fetcher for your data type

| Data type | Primary script | Fallback chain |
|-----------|---------------|----------------|
| Historical OHLCV | `fetch_ohlcv.py` | yfinance only (no good free fallback) |
| Quarterly/annual financials | `fetch_fundamentals.py` | FMP → manual CSV (no good free fallback) |
| Institutional holder count | `fetch_institutional.py` | FMP → none |
| Institutional ownership % | `fetch_institutional.py` | FMP `sharesOutstanding` → Finviz scrape |
| Quote / fast-info | `fetch_ohlcv.py` (function `fast_info`) | yfinance only |

### Step 2: Call the fetcher

All fetchers follow the same pattern: function takes `symbol` (or list) + window, returns a DataFrame or dict. Cache hits return instantly; cache misses fall back to the network.

```python
from scripts.fetch_ohlcv import fetch_ohlcv
df = fetch_ohlcv("AAPL", lookback_days=1500, max_age_hours=24)
```

```python
from scripts.fetch_fundamentals import fetch_quarterly_income
fin = fetch_quarterly_income("NVDA", quarters=8)
```

```python
from scripts.fetch_institutional import fetch_institutional_ownership
own = fetch_institutional_ownership("AAPL")  # tries FMP, falls back to Finviz
```

### Step 3: Cache management

Cache lives at `~/.market_data_cache/` by default. Each fetcher writes:

- `ohlcv/<SYMBOL>.parquet` (or `.json` if pyarrow missing)
- `fundamentals/<SYMBOL>_<period>.json`
- `institutional/<SYMBOL>.json`

Override location with `MARKET_DATA_CACHE` env var.

Cache freshness is enforced by `max_age_hours`. Hit cache fresher than threshold → return cached. Stale or missing → refetch.

To purge: `rm -rf ~/.market_data_cache/` or call `data_cache.clear(category="ohlcv")` for selective clearing.

### Step 4: Rate-limit handling

Each source has its own pacing — handled internally:

- **yfinance**: no explicit limit but spurious 429s observed during heavy parallel use; the helper retries with backoff
- **FMP free tier**: 250 calls/day → 0.3s sleep between calls (250 calls / 86400 s = ~3.5 calls/sec ceiling; conservative)
- **Finviz**: 2.0s sleep between scrapes (avoids IP blocks; user-agent rotation built in)

If you hit rate limits, the call returns `None` with a logged warning rather than raising. The caller is expected to skip that ticker and continue.

### Step 5: Standardized output shapes

OHLCV DataFrame columns (always in this order, always lowercase):

```
date (index, pd.Timestamp)
open, high, low, close, adj_close, volume
```

Fundamentals dict (per period):

```python
{
    "period_end": "YYYY-MM-DD",
    "period_kind": "quarterly" | "annual",
    "revenue": float,
    "eps_basic": float,
    "eps_diluted": float,
    "net_income": float,
    "operating_margin": float,
    # ... see references/output_shapes.md for full list
}
```

Institutional ownership dict:

```python
{
    "symbol": "AAPL",
    "source": "fmp" | "finviz",
    "holder_count": int,
    "ownership_pct": float,        # 0-100
    "shares_held": int,
    "as_of": "YYYY-MM-DD",
}
```

## Output

By default the scripts write to disk cache and return Python objects. For CLI usage:

```bash
python scripts/fetch_ohlcv.py AAPL --lookback-days 1500 --output-csv aapl.csv
python scripts/fetch_fundamentals.py NVDA --quarters 8 --output-json nvda.json
python scripts/fetch_institutional.py AAPL MSFT NVDA --output-json holders.json
```

## Resources

- `scripts/fetch_ohlcv.py` — yfinance-based OHLCV fetcher with parquet caching
- `scripts/fetch_fundamentals.py` — FMP financials (quarterly + annual income / ratios)
- `scripts/fetch_institutional.py` — FMP institutional holders + Finviz ownership-pct fallback
- `scripts/data_cache.py` — shared disk-cache helper (parquet / JSON)
- `references/source_priority.md` — which source to prefer for which field, and why
- `references/output_shapes.md` — full field reference for every fetcher's return value
- `references/rate_limits.md` — observed limits and how the helpers space requests

## Critical Reminders

**This skill is read-only for external services.** It never writes back to FMP, never posts to Finviz. Cache writes are local only.

**API keys are environment variables.** Never hardcode `FMP_API_KEY`. The scripts read from `os.environ` and fail gracefully (returning `None`) if a key is missing.

**Finviz is a courtesy scrape.** Respect the 2-second pacing. If the user needs more than ~50 calls/minute on Finviz, they should pay for Finviz Elite (which has an API).

**yfinance returns auto-adjusted prices by default.** Splits and dividends are reflected in the close column. If you need raw, set `auto_adjust=False` (the script exposes this as a flag). For most backtest use cases, auto-adjusted is what you want.

**Cache invalidation is your responsibility.** A `max_age_hours=24` cache means stale data after a day. For backtests this is fine; for daily-refresh workflows, set `max_age_hours=4` or call with `force_refresh=True` after market close.
