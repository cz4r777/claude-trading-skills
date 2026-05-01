# Rate-limit reference

Observed limits per source and how the helpers space requests.

## yfinance

**Documented limit:** none. Yahoo's public endpoint has no published quota.

**Observed reality:**
- Sequential calls of 1-2 / second sustain indefinitely
- Bursts of 10+ / second see occasional `429 Too Many Requests`
- The endpoint sometimes returns an empty DataFrame instead of an error — detected and treated as a fetch failure

**Helper behavior:**
- No proactive sleep between sequential calls (it's free, why slow it down)
- Retry up to 2 times on empty / failing response with linear backoff (1s, 2s)
- Cache hit when fresh — no network call

**Heavy usage tip:** if you need >100 OHLCV pulls in one run, populate the cache once with `force_refresh=True` overnight, then run your workload against the warm cache during the day.

## FMP (Financial Modeling Prep)

**Documented limits:**
- Free tier: 250 API calls / day
- Starter ($29/mo): 750 calls / day
- Premium ($99/mo): 3,000 calls / day
- Daily quota resets at midnight UTC

**Observed reality:**
- Hard 429 when daily quota exceeded (no retry-after header, just retry tomorrow)
- Soft 429 on burst > ~10 calls / second — recoverable with a sleep

**Helper behavior:**
- 0.3s sleep between every call (bounds peak QPS at ~3.3 / second, well under burst limit)
- On 429: 60-second sleep then one retry; if still 429, fail-soft and return None
- Cache hits don't increment quota — repeat fetches within `max_age_hours` are free

**Quota math for screening 40 stocks (CANSLIM-style):**
- 4-7 endpoints / stock: profile, quote, income (×2), historical (×2), institutional → 5-7 calls / stock
- 40 stocks × 6 calls = 240 calls + ~5 for benchmark data = 245
- That's 98% of the 250-call free-tier budget. Run once / day max on free tier.

**Helper note:** the daily quota is *per API key*, not per IP. If multiple skills share `FMP_API_KEY`, they share the budget. Plan for that.

## Finviz

**Documented limit:** Finviz publishes no rate limit for the free site. Their TOS prohibits "scraping" but the scrape is a single quote page per ticker.

**Observed reality:**
- 1 call / second sustains for ~30 minutes before User-Agent gets blocked
- 1 call / 2 seconds sustains indefinitely (tested up to several hundred / day)
- On block: HTTP 200 with bot-check HTML body — must rotate UA

**Helper behavior:**
- 2.0s sleep between every Finviz call (matches the safe ceiling)
- User-Agent rotation across 2 desktop UAs per call
- On non-200 response: returns None (caller logs and continues)
- No retry — better to skip the ticker than hammer the endpoint

**Heavy usage:** if you do more than ~50 Finviz calls / minute, **pay for Finviz Elite**. Their API has an actual contract; the free scrape is meant for ad-hoc use.

## Combined workflow rate budgeting

A typical workflow that uses all three:

```
Per ticker:
  yfinance OHLCV       — ~0.5s + cache read
  FMP fundamentals     — ~0.3s + 0.3s sleep + cache read
  FMP institutional    — ~0.3s + 0.3s sleep + cache read
  Finviz fallback (10-20% of tickers): + 2.0s
```

Worst-case end-to-end per ticker: ~3-4 seconds.
Cold-cache run for 50 tickers: ~3 minutes.
Warm-cache run for 50 tickers: ~5 seconds (cache hits dominate).

## Knowing when you've hit a limit

The helpers print stderr lines like:

```
WARN: FMP income-statement/NVDA failed: 429 Client Error
WARN: fetch_ohlcv(XYZ) failed: empty response
```

After the first WARN, expect more — most rate limits are batched, so once one fails, the next several will too. Solutions:

1. **Sleep and retry tomorrow** (FMP daily quota — no other fix)
2. **Reduce universe** with `--max-candidates 30` style flags in screeners
3. **Upgrade plan** ($29/mo for FMP is well worth it for serious screeners)
4. **Pre-warm cache overnight** with `force_refresh=True` so the day's runs are cache hits

## What this skill does NOT do

- **No proxy / VPN rotation.** If your IP gets blocked by Finviz, sleep an hour and try again, or switch to Finviz Elite.
- **No request distribution across multiple API keys.** One `FMP_API_KEY` per process. If you need more, run multiple processes with different keys.
- **No streaming / WebSocket support.** EOD-ish polling only.
- **No automatic plan upgrade prompts.** If you blow your free-tier quota, the helper logs the 429 and you decide what to do.
