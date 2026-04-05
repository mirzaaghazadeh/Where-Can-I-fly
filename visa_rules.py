"""
Visa rules powered by Passport Index dataset (199 countries).
Data source: https://github.com/ilyankou/passport-index-dataset

CSV values:
  - number (7, 14, 30, 90, etc.) = visa-free for N days
  - "visa free"    = unrestricted (e.g. EU freedom of movement)
  - "visa on arrival" = granted at border
  - "eta"          = electronic travel authorization
  - "e-visa"       = online visa application
  - "visa required"= embassy visa needed
  - "no admission" = entry banned
  - -1             = same country (self)
"""

import csv
import os

DATA_FILE = os.path.join(os.path.dirname(__file__), "passport-index-data.csv")

# Countries in the Schengen area
SCHENGEN_COUNTRIES = {
    "AT", "BE", "CH", "CZ", "DE", "DK", "EE", "ES", "FI", "FR",
    "GR", "HR", "HU", "IS", "IT", "LI", "LT", "LU", "LV", "MT",
    "NL", "NO", "PL", "PT", "SE", "SI", "SK",
}

# Estimated processing days by visa type
PROCESSING_DAYS = {
    "free": 0,
    "on_arrival": 0,
    "eta": 3,
    "e_visa": 5,
    "schengen": 45,
    "required": 30,
    "no_admission": 999,
}

# Cache: loaded once per run
_visa_data: dict[tuple[str, str], dict] | None = None


def _load_data() -> dict[tuple[str, str], dict]:
    """Load the Passport Index CSV into a lookup dict."""
    global _visa_data
    if _visa_data is not None:
        return _visa_data

    _visa_data = {}
    with open(DATA_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            passport = row["Passport"].strip().upper()
            dest = row["Destination"].strip().upper()
            raw = row["Requirement"].strip().lower()

            # Parse the requirement
            visa_type, days, note = _parse_requirement(raw)

            _visa_data[(passport, dest)] = {
                "visa_type": visa_type,
                "processing_days": days,
                "note": note,
            }

    return _visa_data


def _parse_requirement(raw: str) -> tuple[str, int, str]:
    """Parse a raw requirement string into (visa_type, processing_days, note)."""
    # Numeric = visa-free for N days
    try:
        num = int(raw)
        if num == -1:
            return ("free", 0, "Home country")
        return ("free", 0, f"{num} days visa-free")
    except ValueError:
        pass

    if raw == "visa free":
        return ("free", 0, "Visa-free access")
    if raw == "visa on arrival":
        return ("on_arrival", 0, "Visa on arrival")
    if raw == "eta":
        return ("eta", 3, "Electronic travel authorization (~3 days)")
    if raw == "e-visa":
        return ("e_visa", 5, "e-Visa available (~3-5 days online)")
    if raw == "visa required":
        return ("required", 30, "Embassy visa required")
    if raw == "no admission":
        return ("no_admission", 999, "Entry not permitted")

    # Fallback
    return ("required", 30, f"Unknown requirement: {raw}")


def get_visa_info(citizenship: str, destination: str, has_schengen: bool) -> dict:
    """Return visa requirement for a citizenship -> destination pair."""
    citizenship = citizenship.upper()
    destination = destination.upper()
    data = _load_data()

    # If destination is Schengen and user has Schengen visa, override
    if destination in SCHENGEN_COUNTRIES and has_schengen:
        return {"visa_type": "schengen", "processing_days": 0,
                "note": "Your Schengen visa covers this"}

    # Look up in Passport Index data
    info = data.get((citizenship, destination))
    if info:
        # For Schengen countries that require a visa, label them as schengen type
        if destination in SCHENGEN_COUNTRIES and info["visa_type"] == "required":
            return {"visa_type": "schengen", "processing_days": 45,
                    "note": "Schengen visa required — apply at embassy (~30-60 days)"}
        return info

    # Fallback if pair not in dataset
    return {"visa_type": "required", "processing_days": 30,
            "note": "Not in database — check embassy"}


def can_make_it(visa_info: dict, days_until_flight: int) -> dict:
    """Check if there's enough time to get the visa before the flight."""
    vtype = visa_info["visa_type"]

    if vtype in ("free", "on_arrival"):
        return {"feasible": True, "message": f"No visa hassle — {visa_info['note']}"}

    if vtype == "eta":
        ok = days_until_flight >= 5
        if ok:
            return {"feasible": True,
                    "message": f"ETA needed (~3 days online) — you have {days_until_flight} days. Easy!"}
        return {"feasible": False,
                "message": f"ETA needs ~3 days but flight is in {days_until_flight} days. Very tight!"}

    if vtype == "e_visa":
        ok = days_until_flight >= visa_info["processing_days"] + 2
        if ok:
            return {"feasible": True,
                    "message": f"e-Visa ~{visa_info['processing_days']} days — you have {days_until_flight} days. Doable!"}
        return {"feasible": False,
                "message": f"e-Visa needs ~{visa_info['processing_days']} days but flight is in {days_until_flight} days. Tight!"}

    if vtype == "schengen":
        if visa_info["processing_days"] == 0:
            return {"feasible": True, "message": "Your Schengen visa covers this."}
        ok = days_until_flight >= visa_info["processing_days"]
        if ok:
            return {"feasible": True,
                    "message": f"Schengen visa needed (~{visa_info['processing_days']}d). You have {days_until_flight} days — possible if you apply NOW."}
        return {"feasible": False,
                "message": f"Schengen visa takes ~{visa_info['processing_days']}d. Only {days_until_flight} days left. Probably too late."}

    if vtype == "no_admission":
        return {"feasible": False,
                "message": f"Entry not permitted for your passport."}

    # Embassy visa
    ok = days_until_flight >= visa_info["processing_days"] + 7
    if ok:
        return {"feasible": True,
                "message": f"Embassy visa ~{visa_info['processing_days']}d. You have {days_until_flight} days — start ASAP."}
    return {"feasible": False,
            "message": f"Embassy visa ~{visa_info['processing_days']}d but only {days_until_flight} days left. Likely too late."}
