"""
Flight search using Skyscanner's explore API.
Two-step search:
  1. Search "everywhere" → get countries + entityIds + cheapest price
  2. For each affordable country → get city-level prices + hotel prices

Supports two modes:
  - month: search by month (default)
  - weekend: search specific Fri→Sun date pairs
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta


# Skyscanner sky codes that differ from ISO2
SKY_TO_ISO2 = {
    "UK": "GB",
    "KV": "XK",
}

# Known Skyscanner entity IDs for origin airports/cities
ORIGIN_ENTITIES = {
    "IST": "27542903",
    "IKA": "27539604",
    "DXB": "27537449",
    "SAW": "27542903",
    "ESB": "27539525",
    "AYT": "27539527",
}

API_URL = "https://www.skyscanner.com.tr/g/radar/api/v2/web-unified-search/"

HEADERS_BASE = [
    "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:149.0) Gecko/20100101 Firefox/149.0",
    "-H", "Accept: application/json",
    "-H", "Accept-Language: en-US,en;q=0.9",
    "-H", "Content-Type: application/json",
    "-H", "X-Skyscanner-ChannelId: banana",
    "-H", "X-Skyscanner-DeviceDetection-IsMobile: false",
    "-H", "X-Skyscanner-DeviceDetection-IsTablet: false",
    "-H", "X-Skyscanner-Market: TR",
    "-H", "X-Skyscanner-Locale: en-US",
    "-H", "X-Skyscanner-Currency: USD",
    "-H", "X-Skyscanner-Skip-Accommodation-Carhire: true",
    "-H", "X-Radar-Combined-Explore-Unfocused-Locations-Use-Real-Data: 1",
    "-H", "X-Radar-Combined-Explore-Generic-Results: 1",
    "-H", "X-Skyscanner-Combined-Results-Hotel-Polling: true",
    "-H", "Origin: https://www.skyscanner.com.tr",
    "-H", "Referer: https://www.skyscanner.com.tr/",
]


def _sky_code_to_iso2(sky_code: str) -> str:
    return SKY_TO_ISO2.get(sky_code, sky_code)


def _parse_hotel_price(price_str: str | None) -> float | None:
    if not price_str:
        return None
    match = re.search(r'[\d,]+(?:\.\d+)?', price_str.replace(',', ''))
    if match:
        return float(match.group())
    return None


def _load_cookies() -> str:
    from cookie_fetcher import get_cookies
    return get_cookies()


def _api_call(body: str, cookies: str) -> dict | None:
    cmd = [
        "curl", "-s", "--compressed", "-X", "POST", API_URL,
        *HEADERS_BASE,
        "-H", f"Cookie: {cookies}",
        "--data-raw", body,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        if data.get("reason") == "blocked":
            return {"_blocked": True}
        if data.get("status") == "400":
            return {"_blocked": True}
        return data
    except Exception:
        return None


def _make_date_obj(year: int, month: int, day: int = None):
    """Build Skyscanner date object — month-level or specific date."""
    if day:
        return {"@type": "date", "year": year, "month": month, "day": day}
    return {"@type": "month", "year": year, "month": month}


def _search_everywhere(origin_entity: str, adults: int, out_date, in_date, cookies: str) -> list[dict]:
    """Step 1: Search everywhere, return country-level results with entityIds."""
    body = json.dumps({
        "cabinClass": "ECONOMY",
        "childAges": [],
        "adults": adults,
        "legs": [
            {
                "legOrigin": {"@type": "entity", "entityId": origin_entity},
                "legDestination": {"@type": "everywhere"},
                "dates": out_date,
            },
            {
                "legOrigin": {"@type": "everywhere"},
                "legDestination": {"@type": "entity", "entityId": origin_entity},
                "dates": in_date,
            },
        ],
        "options": {"fareAttributes": {"selectedFareAttributes": []}},
    })

    data = _api_call(body, cookies)
    if not data or data.get("_blocked"):
        return []

    countries = []
    for r in data.get("everywhereDestination", {}).get("results", []):
        if r.get("type") != "LOCATION":
            continue
        content = r.get("content", {})
        location = content.get("location", {})
        cheapest = content.get("flightQuotes", {}).get("cheapest", {})
        if not cheapest:
            continue

        countries.append({
            "entity_id": location.get("id"),
            "sky_code": location.get("skyCode", ""),
            "country_name": location.get("name", ""),
            "price": cheapest.get("rawPrice", 9999),
            "direct": cheapest.get("direct", False),
        })

    return countries


def _search_country(origin_entity: str, country_entity: str, adults: int, out_date, in_date, cookies: str) -> list[dict]:
    """Step 2: Drill into a country, return city-level results with hotel prices."""
    body = json.dumps({
        "cabinClass": "ECONOMY",
        "childAges": [],
        "adults": adults,
        "legs": [
            {
                "legOrigin": {"@type": "entity", "entityId": origin_entity},
                "legDestination": {"@type": "entity", "entityId": country_entity},
                "dates": out_date,
                "placeOfStay": country_entity,
            },
            {
                "legOrigin": {"@type": "entity", "entityId": country_entity},
                "legDestination": {"@type": "entity", "entityId": origin_entity},
                "dates": in_date,
            },
        ],
        "options": {"fareAttributes": {"selectedFareAttributes": []}},
    })

    data = _api_call(body, cookies)
    if not data or data.get("_blocked"):
        return None  # None = blocked/error, distinct from [] = no cities

    cities = []
    for r in data.get("countryDestination", {}).get("results", []):
        if r.get("type") != "LOCATION":
            continue
        content = r.get("content", {})
        location = content.get("location", {})
        cheapest = content.get("flightQuotes", {}).get("cheapest", {})
        direct_quote = content.get("flightQuotes", {}).get("direct")
        if not cheapest:
            continue

        direct_price = None
        if direct_quote:
            direct_price = direct_quote.get("rawPrice")

        hotel_quote = content.get("hotelQuotes", {}).get("standard", {})
        hotel_price = _parse_hotel_price(hotel_quote.get("price"))

        cities.append({
            "city_name": location.get("name", ""),
            "city_type": location.get("type", ""),
            "price": cheapest.get("rawPrice", 9999),
            "direct": cheapest.get("direct", False),
            "direct_price": direct_price,
            "has_direct_route": content.get("flightRoutes", {}).get("directFlightsAvailable", False),
            "hotel_per_night": hotel_price,
        })

    return sorted(cities, key=lambda c: c["price"])


def _get_upcoming_weekends(search_days: int) -> list[tuple[datetime, datetime]]:
    """Get upcoming Fri→Sun pairs within search_days."""
    weekends = []
    today = datetime.now()
    d = today + timedelta(days=1)
    end = today + timedelta(days=search_days)

    while d <= end:
        if d.weekday() == 4:  # Friday
            fri = d
            sun = fri + timedelta(days=2)
            weekends.append((fri, sun))
        d += timedelta(days=1)

    return weekends


def search_skyscanner(origin: str, max_price: int, search_days: int, travelers: int = 1, weekend: bool = False) -> list[dict]:
    """Two-step Skyscanner search: countries → cities with hotel prices."""
    origin_entity = ORIGIN_ENTITIES.get(origin.upper())
    if not origin_entity:
        print(f"  [Skyscanner: unknown origin '{origin}' — add its entityId to ORIGIN_ENTITIES]")
        return []

    cookies = _load_cookies()
    if not cookies:
        print("  [Could not get Skyscanner cookies]")
        return []

    # Build list of (out_date, in_date, label) to search
    if weekend:
        weekends = _get_upcoming_weekends(search_days)
        if not weekends:
            print("  [No weekends found in search window]")
            return []
        # Limit to 4 weekends to reduce API calls
        weekends = weekends[:4]
        print(f"  [Weekend mode: checking {len(weekends)} upcoming Fri→Sun weekends]")
        date_pairs = []
        for fri, sun in weekends:
            out = _make_date_obj(fri.year, fri.month, fri.day)
            ret = _make_date_obj(sun.year, sun.month, sun.day)
            label = f"{fri.strftime('%b %d')}"
            date_pairs.append((out, ret, label))
    else:
        now = datetime.now()
        date_pairs = []
        seen = set()
        for offset in range(3):
            dt = now + timedelta(days=30 * offset)
            ym = (dt.year, dt.month)
            if ym not in seen:
                seen.add(ym)
                out = _make_date_obj(dt.year, dt.month)
                date_pairs.append((out, out, f"{dt.year}-{dt.month:02d}"))

    # Step 1: Get all countries across date ranges
    print("  [Step 1: Searching all destinations...]")
    all_countries = {}

    for out_date, in_date, label in date_pairs:
        countries = _search_everywhere(origin_entity, travelers, out_date, in_date, cookies)
        if not countries:
            print(f"  [Skyscanner blocked or no data for {label}]")
            # Try refreshing cookies on first failure
            cookies = _load_cookies()
            time.sleep(1)
            countries = _search_everywhere(origin_entity, travelers, out_date, in_date, cookies)
            if not countries:
                continue

        print(f"  [  {label}: {len(countries)} countries]")
        for c in countries:
            key = c["sky_code"]
            if key not in all_countries or c["price"] < all_countries[key]["price"]:
                all_countries[key] = {**c, "out_date": out_date, "in_date": in_date, "label": label}

        time.sleep(0.5)

    if not all_countries:
        return []

    # Filter to affordable countries
    affordable = {k: v for k, v in all_countries.items() if v["price"] <= max_price}
    print(f"  [Found {len(affordable)} countries with flights under ${max_price}]")

    # Step 2: Drill into each country for city-level prices + hotels
    print(f"  [Step 2: Getting city & hotel details for {len(affordable)} countries...]")
    all_flights = []
    blocked_count = 0

    for sky_code, country in affordable.items():
        country_code = _sky_code_to_iso2(sky_code)

        time.sleep(0.5)

        cities = _search_country(
            origin_entity, country["entity_id"], travelers,
            country["out_date"], country["in_date"], cookies
        )

        # If blocked, try refreshing cookies
        if cities is None:
            blocked_count += 1
            if blocked_count <= 2:
                print(f"  [Blocked — refreshing cookies...]")
                cookies = _load_cookies()
                time.sleep(1)
                cities = _search_country(
                    origin_entity, country["entity_id"], travelers,
                    country["out_date"], country["in_date"], cookies
                )

        if not cities:
            all_flights.append({
                "origin": origin,
                "dest": country["country_name"],
                "dest_country": country_code,
                "city": country["country_name"],
                "price": country["price"],
                "currency": "USD",
                "airline": "Direct" if country["direct"] else "1+ stop",
                "departure": country["label"],
                "direct": country["direct"],
                "direct_price": None,
                "has_direct_route": country["direct"],
                "hotel_per_night": None,
            })
            continue

        for city in cities[:3]:
            if city["price"] > max_price:
                continue
            all_flights.append({
                "origin": origin,
                "dest": country["country_name"],
                "dest_country": country_code,
                "city": city["city_name"],
                "price": city["price"],
                "currency": "USD",
                "airline": "Direct" if city["direct"] else "1+ stop",
                "departure": country["label"],
                "direct": city["direct"],
                "direct_price": city["direct_price"],
                "has_direct_route": city["has_direct_route"],
                "hotel_per_night": city["hotel_per_night"],
            })

    return sorted(all_flights, key=lambda f: f["price"])


def search_flights(origin: str, max_price: int, search_days: int, travelers: int = 1, weekend: bool = False) -> list[dict]:
    """Search for cheap flights via Skyscanner."""
    mode = "weekend (Fri→Sun)" if weekend else "flexible"
    print(f"  [Searching Skyscanner for {travelers} traveler(s), mode: {mode}]")
    flights = search_skyscanner(origin, max_price, search_days, travelers, weekend)
    if flights:
        print(f"  [Found {len(flights)} city destinations]")
        return flights

    print("  [No results from Skyscanner]")
    return []
