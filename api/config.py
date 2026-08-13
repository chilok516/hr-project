import os
from pathlib import Path

# Support Docker volume mount (/data) and local dev (../data relative to api/)
DATA_ROOT = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))

ROOT = Path(__file__).parent
DATA_RAW = DATA_ROOT / "raw"
DATA_PROCESSED = DATA_ROOT / "processed"
DATA_MODELS = DATA_ROOT / "models"

for d in [DATA_RAW, DATA_PROCESSED, DATA_MODELS]:
    d.mkdir(parents=True, exist_ok=True)

# HKJC venues
VENUES = {"ST": "Sha Tin", "HV": "Happy Valley"}

# Race classes (HK system: 1-5, with G1/G2/G3 for group races)
CLASSES = ["G1", "G2", "G3", "1", "2", "3", "4", "5"]

# Distances in metres
DISTANCES = [1000, 1200, 1400, 1600, 1650, 1800, 2000, 2200, 2400]

# Track conditions
GOINGS = {
    "GD": "Good",
    "GF": "Good to Firm",
    "G": "Good",
    "Y": "Yielding",
    "YL": "Yielding to Soft",
    "S": "Soft",
    "H": "Heavy",
    "GD-Y": "Good to Yielding",
    "WF": "Wet Fast",
    "SLOW": "Slow",
    "ST": "Standard",
}

HKJC_BASE = "https://racing.hkjc.com"
HKJC_RESULTS = f"{HKJC_BASE}/racing/information/English/Racing/ResultsAll.aspx"
HKJC_HORSE = f"{HKJC_BASE}/racing/information/English/Horse/Horse.aspx"
HKJC_RACECARD = f"{HKJC_BASE}/racing/information/English/Racing/RaceCard.aspx"
HKJC_FORM = f"{HKJC_BASE}/racing/information/English/Horse/Form.aspx"

# Backtest parameters (aligned with Jacky's risk profile)
BET_SIZE = 100  # unit bet per race
STARTING_BANKROLL = 100_000
MAX_DAILY_LOSS = 2_000
MAX_WEEKLY_LOSS = 5_000
MAX_BETS_PER_DAY = 5
