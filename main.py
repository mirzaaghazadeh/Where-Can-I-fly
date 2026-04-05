#!/usr/bin/env python3
"""
Flight Finder — finds cheap flights + hotels from Skyscanner, checks visa feasibility.
Opens results in browser as an interactive HTML report.

Usage:
  python main.py              # search by month (default)
  python main.py --weekend    # search Fri→Sun weekends only
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

from flight_search import search_flights
from visa_rules import get_visa_info, can_make_it
from html_report import open_report


def build_trips(flights, citizenship, has_schengen, travelers, max_price, trip_nights):
    easy, doable, hard = [], [], []

    for flight in flights:
        dest_country = flight["dest_country"]
        country_name = flight.get("dest", dest_country)
        visa_info = get_visa_info(citizenship, dest_country, has_schengen)

        dep = flight.get("departure", "")
        if dep and len(dep) == 10:
            dep_date = datetime.strptime(dep, "%Y-%m-%d")
            days_until = max(1, (dep_date - datetime.now()).days)
        elif dep and len(dep) == 7:
            dep_date = datetime.strptime(dep + "-15", "%Y-%m-%d")
            days_until = max(1, (dep_date - datetime.now()).days)
        else:
            days_until = 30

        feasibility = can_make_it(visa_info, days_until)

        flight_pp = flight["price"] / travelers
        hotel_pn = flight.get("hotel_per_night")
        hotel_total = hotel_pn * trip_nights if hotel_pn else None
        total_pp = flight_pp + hotel_total if hotel_total else None

        if total_pp and total_pp > max_price:
            continue

        city = flight.get("city", "")
        dest_str = f"{city}, {country_name}" if city and city != country_name else country_name

        trip = {
            "dest": dest_str,
            "cc": dest_country,
            "flight_pp": flight_pp,
            "direct": flight.get("direct", False),
            "hotel_pn": hotel_pn,
            "hotel_total": hotel_total,
            "total_pp": total_pp,
            "when": flight.get("departure", "?"),
            "days": days_until,
            "visa_type": visa_info["visa_type"],
            "visa_note": visa_info["note"],
            "feasible": feasibility["feasible"],
            "feas_msg": feasibility["message"],
        }

        if visa_info["visa_type"] in ("free", "on_arrival"):
            easy.append(trip)
        elif feasibility["feasible"]:
            doable.append(trip)
        else:
            hard.append(trip)

    key = lambda t: t["total_pp"] if t["total_pp"] else t["flight_pp"]
    easy.sort(key=key)
    doable.sort(key=key)
    hard.sort(key=key)
    return easy, doable, hard


def main():
    load_dotenv()

    weekend = "--weekend" in sys.argv or "-weekend" in sys.argv

    citizenship = os.getenv("CITIZENSHIP", "IR").upper()
    has_schengen = os.getenv("HAS_SCHENGEN_VISA", "false").lower() == "true"
    home_airport = os.getenv("HOME_AIRPORT", "IKA").upper()
    search_days = int(os.getenv("SEARCH_DAYS_AHEAD", "60"))
    max_price = int(os.getenv("MAX_PRICE_USD", "500"))
    travelers = int(os.getenv("TRAVELERS", "1"))

    trip_nights = 2 if weekend else 5
    mode_str = "Weekend (Fri→Sun)" if weekend else f"{search_days} days ahead"

    print(f"✈️  FLIGHT FINDER {'[WEEKEND]' if weekend else ''}")
    print(f"   {travelers} travelers | {citizenship} passport | Schengen: {'Yes' if has_schengen else 'No'}")
    print(f"   Max ${max_price}/pp | {mode_str} | {trip_nights} nights | From: {home_airport}")
    print()

    print("🔍 Searching flights & hotels...")
    flights = search_flights(home_airport, max_price, search_days, travelers, weekend)

    if not flights:
        print(f"\n❌ No flights found under ${max_price}. Try increasing MAX_PRICE_USD.")
        return

    print(f"  Found {len(flights)} destinations. Checking visas...")

    easy, doable, hard = build_trips(flights, citizenship, has_schengen, travelers, max_price, trip_nights)

    total = len(easy) + len(doable) + len(hard)
    print(f"\n📊 {total} destinations: 🟢 {len(easy)} easy | 🟡 {len(doable)} doable | 🔴 {len(hard)} hard")

    if total == 0:
        print("No destinations within budget after visa check.")
        return

    # Open HTML report in browser
    config = {
        "origin": home_airport,
        "travelers": travelers,
        "max_price": max_price,
        "trip_nights": trip_nights,
        "weekend": weekend,
        "citizenship": citizenship,
        "has_schengen": has_schengen,
        "search_days": search_days,
    }
    open_report(easy, doable, hard, config)


if __name__ == "__main__":
    main()
