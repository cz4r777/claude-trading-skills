# Output shape reference

Every fetcher returns a stable shape so downstream skills can rely on field names. This document is the contract.

## OHLCV — `fetch_ohlcv(symbol, lookback_days)`

Returns: `pandas.DataFrame` indexed by `pd.Timestamp` (date), or `None` on failure.

| column      | dtype | notes |
|-------------|-------|-------|
| `open`      | float | session open (auto-adjusted by default) |
| `high`      | float | session high |
| `low`       | float | session low |
| `close`     | float | session close (auto-adjusted by default) |
| `adj_close` | float | adjusted close (yfinance: same as `close` when `auto_adjust=True`) |
| `volume`    | int   | session volume |

Index name: `date`. Type: `pd.DatetimeIndex`, tz-naive (yfinance returns tz-aware; the helper strips). Sorted ascending.

Length: requested `lookback_days` or fewer (some tickers have shorter histories).

## Quote / fast info — `fast_info(symbol)`

Returns: `dict`.

| key              | type   | notes |
|------------------|--------|-------|
| `symbol`         | string | uppercased |
| `last_price`     | float  | latest available quote |
| `previous_close` | float  | previous session close |
| `change_pct`     | float  | `(last - prev) / prev * 100`, rounded to 2dp |
| `error`          | string | present *only* on failure |

## Quarterly income — `fetch_quarterly_income(symbol, quarters=8)`

Returns: `list[dict]`, newest first, length up to `quarters`. Each dict:

| key              | type    | notes |
|------------------|---------|-------|
| `period_end`     | string  | ISO `YYYY-MM-DD` (period close date) |
| `period_kind`    | string  | `"quarterly"` |
| `revenue`        | float   | total revenue, USD |
| `gross_profit`   | float   | |
| `operating_income` | float | |
| `net_income`     | float   | |
| `eps_basic`      | float   | basic EPS |
| `eps_diluted`    | float   | diluted EPS |
| `shares_basic`   | float   | weighted avg basic shares |
| `shares_diluted` | float   | weighted avg diluted shares |
| `gross_margin`   | float   | `gross_profit / revenue`, 0–1 |
| `operating_margin` | float | `operating_income / revenue`, 0–1 |
| `net_margin`     | float   | `net_income / revenue`, 0–1 |

Any field can be `None` if FMP didn't return it for that period.

## Annual income — `fetch_annual_income(symbol, years=5)`

Same schema as quarterly, but `period_kind` is `"annual"` and there's typically one row per fiscal year.

## Profile — `fetch_profile(symbol)`

Returns: `dict` (passes through FMP's profile shape; **not** renamed). Common keys:

| key              | type   | notes |
|------------------|--------|-------|
| `symbol`         | string | |
| `companyName`    | string | |
| `sector`         | string | e.g. "Technology" |
| `industry`       | string | e.g. "Semiconductors" |
| `mktCap`         | number | market cap in USD |
| `beta`           | number | |
| `country`        | string | ISO-2 |
| `exchange`       | string | e.g. "NASDAQ" |
| `ipoDate`        | string | ISO date |
| `description`    | string | company blurb |

This is the one fetcher whose shape mirrors the upstream API (low value in renaming since fields are mostly self-explanatory). If the FMP profile API changes, this dict's keys may shift.

## Institutional ownership — `fetch_institutional_ownership(symbol)`

Returns: `dict`.

| key                    | type    | notes |
|------------------------|---------|-------|
| `symbol`               | string  | |
| `source`               | string  | one of `"fmp"`, `"finviz"`, `"fmp+finviz"` |
| `holder_count`         | int \| None | number of 13F filers (FMP only; None if from Finviz) |
| `shares_held`          | int \| None | total shares held by 13F filers (FMP only) |
| `shares_outstanding`   | int \| None | (FMP quote) — None if FMP didn't return |
| `ownership_pct`        | float \| None | 0-100; computed (FMP) or scraped (Finviz) |
| `as_of`                | string  | ISO date this fetch happened |

Note: FMP's `institutional-holder` endpoint reports the most recent quarter's 13F-filed positions. Holdings update quarterly (45-day lag); cache TTL is 7 days by default.

## Common patterns

### "Did the fetch succeed?"

Every fetcher returns either the shape documented above, or `None` on failure. Standard pattern:

```python
df = fetch_ohlcv("AAPL", lookback_days=252)
if df is None:
    print("skip AAPL — fetch failed")
    return
# safe to use df below
```

For dict-returning fetchers, also check that critical fields are not `None`:

```python
fin = fetch_quarterly_income("NVDA", quarters=4)
if not fin or fin[0].get("revenue") is None:
    print("skip NVDA — financials incomplete")
    return
```

### "Is this a cache hit or live fetch?"

The fetchers don't currently surface this. If you need to know, set `force_refresh=True` to guarantee a live fetch, or check the cache file's mtime via `data_cache.df_path()` / `data_cache.json_path()`.

### Dataframe vs dict

OHLCV / fast_info return DataFrames or dicts; financials return list-of-dicts. This intentional split reflects that time-series wants pandas semantics while period-stamped financials are simpler as JSON-friendly dicts.
