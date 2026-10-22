from pathlib import Path

# Active trading symbol for the connected MT5 account
SYMBOL = "USTEC"
TIMEFRAME_NAME = "M5"

# Research assumptions
INITIAL_EQUITY = 10_000.0
RISK_PER_TRADE = 0.005   # 0.5%

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)