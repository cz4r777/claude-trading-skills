# Source priority guide

Which data source to prefer for which kind of request, and why.

## Historical OHLCV

**Primary: yfinance.** Free, no key, covers all US-listed equities, ETFs, indices, FX, crypto. Auto-adjusted for splits and dividends by default. Daily resolution.

**Why no fallback:** there's no equivalent free source with the same coverage. Stooq, Tiingo free tier, and Polygon.io free tier all have either narrower universes, lower limits, or both. If yfinance fails for a ticker, the most likely cause is the ticker delisted or symbol changed — log and skip.

**Caveats:**
- yfinance auto-adjusts close prices using the latest split/div schedule. This is correct for backtesting but means raw historical prices in the cache won't match a screen taken on a specific past date.
- Volume data has occasional zeros on illiquid names; the script doesn't repair these — caller should filter.
- yfinance reads from Yahoo's public endpoint, which Yahoo can throttle without notice. The retry-with-backoff helper inside `fetch_ohlcv.py` handles transient 429s.

## Quarterly / annual financials

**Primary: FMP (Financial Modeling Prep).** Quarterly + annual income statements, balance sheets, cash flow, key ratios. Free tier 250 calls/day; Starter $29/month for 750/day.

**Why FMP over alternatives:**
- yfinance's `Ticker.financials` returns inconsistent data — sometimes only annual, sometimes empty for tickers that report — and uses non-standard field names.
- SEC EDGAR XBRL is the canonical source but parsing it is a project, not a fetch.
- Alpha Vantage has a 5-call/minute limit that makes batch screening painful.
- FMP normalizes field names across companies, returns consistent JSON, and has a workable free tier.

**Fallback:** none free. If FMP returns an empty list (the company doesn't report, or the symbol is mismatched), the fetcher returns `None`. The caller should skip that ticker for fundamental-driven workflows.

## Institutional ownership

**Primary: FMP `institutional-holder/{symbol}`.** Returns the list of 13F filers with their share counts. Combined with FMP's `quote/{symbol}.sharesOutstanding`, that gives you holder count and ownership %.

**Fallback: Finviz scrape.** When FMP doesn't return `sharesOutstanding` (happens for ~10-20% of tickers in the free tier — coverage gap, not a 429), the fallback scrapes Finviz's quote page for the "Inst Own" cell. This gives you the ownership % directly, but no holder count.

**Why this two-step is worth it:** institutional ownership is the I in CANSLIM. Without a fallback, ~20% of tickers get a partial score and fall down the rankings unfairly. The Finviz scrape costs 2 seconds per ticker but lifts the hit rate to ~100%.

**Don't scrape Finviz for everything.** Finviz Elite has an API for this; use it if you do more than ~50 calls/minute. The free scrape is for occasional ad-hoc lookups.

## Sector / industry classification

**Primary: FMP profile endpoint.** Sector, industry, market cap, beta, country, exchange. Slowly-changing data — the cache TTL is set to 1 week.

**Fallback: yfinance Ticker.info.** Has the same fields under different names (`sector`, `industry`, `marketCap`). Use only if FMP is unavailable; the field naming is brittle.

## Quotes (live-ish snapshot)

**Primary: yfinance `fast_info`.** Returns last price, previous close, day high/low — about 200ms. Adequate for "what's this ticker doing right now" with an EOD-ish lag.

**Don't use this for live trading.** It's pulled from Yahoo's public quote endpoint with unspecified delay (often 15-20 minutes for non-realtime tickers). For live, use a broker SDK.

## Earnings calendar

**Not in this skill.** Use [earnings-calendar](../../earnings-calendar/) — it's a dedicated FMP-based skill for upcoming earnings dates with mid-cap-and-above filtering.

## Options chains

**Not supported.** yfinance returns *current* chains only and FMP doesn't have historical chains. Use a paid source (CBOE DataShop, ORATS, Polygon options) for historical options work.

## Why this skill exists

Each of the three sources has its own:
- Authentication model (yfinance: none, FMP: API key, Finviz: scrape with UA rotation)
- Rate-limit shape (yfinance: implicit, FMP: hard daily cap, Finviz: per-second courtesy)
- Field naming convention (yfinance Ticker objects, FMP JSON dicts, Finviz HTML cells)
- Failure mode (yfinance: empty df, FMP: empty list, Finviz: HTTP 200 with bot-detection page)

A naive "just call yfinance and FMP and Finviz" implementation in every screener / backtester duplicates this plumbing 5 times across the codebase. This skill centralizes it so:
- Cache hits are shared across skills
- Rate limiters are shared (so two skills running in parallel don't both blast Finviz)
- Field renames happen once
- Failure modes are normalized to "returns None, log and continue"
