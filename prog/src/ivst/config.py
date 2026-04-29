"""Application configuration."""

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_PATH = DATA_DIR / "ivst.db"
CONFIG_DIR = Path.home() / ".config" / "ivst"

CACHE_TTL_PRICES = 3600  # 1 hour
CACHE_TTL_NEWS = 1800  # 30 min
CACHE_TTL_TICKERS = 7 * 86400  # 7 days
CACHE_TTL_MACRO = 3600  # 1 hour


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
