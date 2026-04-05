"""
Generate an HTML report of flight results and open it in the browser.
"""

import os
import urllib.parse
import webbrowser
from datetime import datetime, timedelta


def _make_google_flights_link(origin: str, city_name: str, country_name: str, when: str, travelers: int) -> str:
    """Build a Google Flights search URL."""
    dest = f"{city_name}" if city_name != country_name else country_name
    query = f"flights from {origin} to {dest}"

    # Parse date
    out_date = ""
    in_date = ""
    if len(when) == 7:  # 2026-04
        out_date = f"{when}-15"
        in_date = f"{when}-20"
    elif len(when) >= 5:  # "Apr 10" format
        try:
            dt = datetime.strptime(f"{when} {datetime.now().year}", "%b %d %Y")
            if dt < datetime.now():
                dt = dt.replace(year=dt.year + 1)
            out_date = dt.strftime("%Y-%m-%d")
            ret = dt + timedelta(days=2)
            in_date = ret.strftime("%Y-%m-%d")
        except ValueError:
            pass

    url = f"https://www.google.com/travel/flights?q={urllib.parse.quote(query)}"
    if out_date:
        url += f"&d={out_date}&r={in_date}"
    url += f"&px={travelers}"
    return url


def _visa_badge(visa_type: str) -> str:
    badges = {
        "free": '<span class="badge bg-success">✅ Visa Free</span>',
        "on_arrival": '<span class="badge bg-success">✅ On Arrival</span>',
        "eta": '<span class="badge bg-info">📋 eTA</span>',
        "e_visa": '<span class="badge bg-info">📋 e-Visa</span>',
        "schengen": '<span class="badge bg-warning text-dark">🇪🇺 Schengen</span>',
        "required": '<span class="badge bg-danger">🛂 Visa Required</span>',
        "no_admission": '<span class="badge bg-dark">🚫 No Admission</span>',
    }
    return badges.get(visa_type, f'<span class="badge bg-secondary">{visa_type}</span>')


def _feasibility_icon(feasible: bool) -> str:
    return "👍" if feasible else "⛔"


def _trip_card(trip: dict, origin: str, travelers: int) -> str:
    dest = trip["dest"]
    flight_pp = trip["flight_pp"]
    hotel_pn = trip.get("hotel_pn")
    hotel_total = trip.get("hotel_total")
    total_pp = trip.get("total_pp")
    direct = trip.get("direct", False)
    when = trip.get("when", "?")
    visa_type = trip.get("visa_type", "")
    feasible = trip.get("feasible", False)
    visa_note = trip.get("visa_note", "")
    feas_msg = trip.get("feas_msg", "")

    # Split "City, Country" to get parts
    parts = dest.split(",")
    city_part = parts[0].strip()
    country_part = parts[1].strip() if len(parts) > 1 else city_part
    link = _make_google_flights_link(origin, city_part, country_part, when, travelers)

    direct_badge = '<span class="badge bg-primary">Direct</span>' if direct else '<span class="badge bg-secondary">1+ stop</span>'

    hotel_str = f"${hotel_pn:.0f}/night" if hotel_pn else "N/A"
    hotel_total_str = f"${hotel_total:.0f}" if hotel_total else "—"
    total_str = f"${total_pp:.0f}" if total_pp else f"~${flight_pp:.0f}"

    return f"""
    <div class="col-md-6 col-lg-4 mb-3">
      <div class="card h-100 shadow-sm">
        <div class="card-body">
          <h5 class="card-title mb-1">{dest}</h5>
          <div class="mb-2">{direct_badge} {_visa_badge(visa_type)}</div>
          <div class="row text-center mb-2">
            <div class="col-4">
              <div class="text-muted small">Flight/pp</div>
              <div class="fw-bold text-primary">${flight_pp:.0f}</div>
            </div>
            <div class="col-4">
              <div class="text-muted small">Hotel</div>
              <div class="fw-bold text-warning">{hotel_str}</div>
            </div>
            <div class="col-4">
              <div class="text-muted small">Total/pp</div>
              <div class="fw-bold text-success fs-5">{total_str}</div>
            </div>
          </div>
          <div class="small text-muted mb-2">
            📅 {when} &nbsp; {_feasibility_icon(feasible)} {feas_msg}
          </div>
          <div class="small text-muted mb-2">{visa_note}</div>
          <a href="{link}" target="_blank" class="btn btn-outline-primary btn-sm w-100">
            🔍 Search on Google Flights
          </a>
        </div>
      </div>
    </div>
    """


def generate_html(easy, doable, hard, config: dict) -> str:
    """Generate full HTML report."""
    origin = config["origin"]
    travelers = config["travelers"]
    max_price = config["max_price"]
    trip_nights = config["trip_nights"]
    weekend = config.get("weekend", False)
    citizenship = config.get("citizenship", "?")
    has_schengen = config.get("has_schengen", False)

    mode_str = "Weekend (Fri→Sun)" if weekend else f"{config.get('search_days', 60)} days ahead"

    sections = []

    if easy:
        cards = "".join(_trip_card(t, origin, travelers) for t in easy)
        sections.append(f"""
        <h3 class="mt-4 text-success">🟢 Easy — No Visa Needed ({len(easy)})</h3>
        <div class="row">{cards}</div>
        """)

    if doable:
        cards = "".join(_trip_card(t, origin, travelers) for t in doable)
        sections.append(f"""
        <h3 class="mt-4 text-warning">🟡 Doable — Visa Needed, Time Enough ({len(doable)})</h3>
        <div class="row">{cards}</div>
        """)

    if hard:
        cards = "".join(_trip_card(t, origin, travelers) for t in hard)
        sections.append(f"""
        <h3 class="mt-4 text-danger">🔴 Hard — Probably Too Late ({len(hard)})</h3>
        <div class="row">{cards}</div>
        """)

    total = len(easy) + len(doable) + len(hard)
    sections_html = "\n".join(sections)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Flight Finder Results</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background: #f8f9fa; }}
        .card:hover {{ transform: translateY(-2px); transition: 0.2s; box-shadow: 0 4px 15px rgba(0,0,0,0.15) !important; }}
        .hero {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem 0; }}
        .badge {{ font-size: 0.75em; }}
        .stat-box {{ background: rgba(255,255,255,0.15); border-radius: 10px; padding: 10px 15px; }}
    </style>
</head>
<body>
    <div class="hero">
        <div class="container">
            <h1>✈️ Flight Finder</h1>
            <div class="d-flex flex-wrap gap-3 mt-3">
                <div class="stat-box">👥 {travelers} Traveler(s)</div>
                <div class="stat-box">🛂 Passport: {citizenship}</div>
                <div class="stat-box">🇪🇺 Schengen: {"Yes ✅" if has_schengen else "No ❌"}</div>
                <div class="stat-box">💰 Max: ${max_price}/pp</div>
                <div class="stat-box">🗓️ {mode_str}</div>
                <div class="stat-box">🏨 {trip_nights} nights</div>
                <div class="stat-box">🏠 From: {origin}</div>
            </div>
            <div class="mt-3">
                <span class="badge bg-light text-dark fs-6">📊 {total} destinations</span>
                <span class="badge bg-success fs-6">🟢 {len(easy)} easy</span>
                <span class="badge bg-warning text-dark fs-6">🟡 {len(doable)} doable</span>
                <span class="badge bg-danger fs-6">🔴 {len(hard)} hard</span>
            </div>
        </div>
    </div>

    <div class="container py-4">
        {sections_html}

        <hr class="my-4">
        <p class="text-muted small text-center">
            Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} &bull;
            D = Direct, S = 1+ stop &bull;
            Prices per person (flight + {trip_nights}n hotel) &bull;
            Data: Skyscanner + Passport Index
        </p>
    </div>
</body>
</html>"""
    return html


def open_report(easy, doable, hard, config: dict):
    """Generate HTML report and open in browser."""
    html = generate_html(easy, doable, hard, config)

    report_path = os.path.join(os.path.dirname(__file__), "report.html")
    with open(report_path, "w") as f:
        f.write(html)

    webbrowser.open(f"file://{os.path.abspath(report_path)}")
    print(f"  [Report opened in browser: {report_path}]")
