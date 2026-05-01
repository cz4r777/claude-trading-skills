"""Shared disk cache for the market-data-fetcher scripts.

Cache lives at ~/.market_data_cache (override via MARKET_DATA_CACHE env var).
Each category gets its own subdirectory. OHLCV uses parquet when pyarrow is
available, JSON otherwise. Fundamentals + institutional use JSON.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import pyarrow  # noqa: F401
    HAS_PARQUET = True
except ImportError:
    HAS_PARQUET = False


def cache_root() -> Path:
    root = Path(os.environ.get("MARKET_DATA_CACHE", str(Path.home() / ".market_data_cache")))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cat_dir(category: str) -> Path:
    d = cache_root() / category
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_fresh(path: Path, max_age_hours: float) -> bool:
    if not path.exists():
        return False
    age = (time.time() - path.stat().st_mtime) / 3600
    return age <= max_age_hours


# --- DataFrame cache (OHLCV) ---

def df_path(category: str, symbol: str) -> Path:
    ext = "parquet" if HAS_PARQUET else "json"
    return _cat_dir(category) / f"{symbol.upper()}.{ext}"


def get_df(category: str, symbol: str, max_age_hours: float = 24.0):
    if not HAS_PANDAS:
        return None
    path = df_path(category, symbol)
    if not _is_fresh(path, max_age_hours):
        return None
    try:
        if path.suffix == ".parquet":
            return pd.read_parquet(path)
        return pd.read_json(path, orient="split")
    except Exception:
        return None


def put_df(category: str, symbol: str, df) -> None:
    if not HAS_PANDAS or df is None or len(df) == 0:
        return
    path = df_path(category, symbol)
    try:
        if path.suffix == ".parquet":
            df.to_parquet(path)
        else:
            df.to_json(path, orient="split", date_format="iso")
    except Exception:
        pass


# --- JSON cache (fundamentals, institutional) ---

def json_path(category: str, key: str) -> Path:
    return _cat_dir(category) / f"{key}.json"


def get_json(category: str, key: str, max_age_hours: float = 24.0) -> Any | None:
    path = json_path(category, key)
    if not _is_fresh(path, max_age_hours):
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def put_json(category: str, key: str, value: Any) -> None:
    path = json_path(category, key)
    try:
        path.write_text(json.dumps(value, indent=2, default=str))
    except Exception:
        pass


# --- Maintenance ---

def clear(category: str | None = None) -> int:
    """Remove cached files. Returns count removed."""
    if category:
        d = _cat_dir(category)
        if not d.exists():
            return 0
        n = 0
        for f in d.iterdir():
            if f.is_file():
                f.unlink()
                n += 1
        return n
    # All categories
    n = 0
    for sub in cache_root().iterdir():
        if sub.is_dir():
            for f in sub.iterdir():
                if f.is_file():
                    f.unlink()
                    n += 1
    return n
