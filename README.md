# Flight Finder

Find cheap flights + hotels from Skyscanner and check visa feasibility based on your passport — all in one interactive HTML report.

![Python](https://img.shields.io/badge/Python-3.12+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## What it does

1. Searches Skyscanner for cheap flights from your home airport
2. Fetches hotel prices for each destination
3. Checks visa requirements using [Passport Index](https://github.com/ilyankou/passport-index-dataset) data (199 countries)
4. Categorizes destinations into **Easy** (visa-free), **Doable** (visa needed but enough time), and **Hard** (probably too late)
5. Opens a beautiful HTML report in your browser with Google Flights links

## Quick Start

```bash
# Clone and setup
git clone https://github.com/YOUR_USERNAME/flight-finder.git
cd flight-finder
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install firefox

# Configure
cp .env.example .env
# Edit .env with your details

# Run
python main.py              # search by month (default)
python main.py --weekend    # search Fri→Sun weekends only
```

## Configuration

Edit `.env` to customize:

| Variable | Description | Default |
|---|---|---|
| `CITIZENSHIP` | Your passport country code (ISO 2-letter) | `IR` |
| `HAS_SCHENGEN_VISA` | Do you hold a Schengen visa? | `false` |
| `HOME_AIRPORT` | Departure airport IATA code | `IST` |
| `SEARCH_DAYS_AHEAD` | How far ahead to search | `60` |
| `TRAVELERS` | Number of travelers | `1` |
| `MAX_PRICE_USD` | Max budget per person (flight + hotel) | `500` |

### Supported Origin Airports

IST, IKA, DXB, SAW, ESB, AYT — add more in `flight_search.py` (`ORIGIN_ENTITIES`).

## How It Works

- **Flight data**: Skyscanner explore API (cookies extracted from your Firefox browser or via captcha solve)
- **Visa data**: Passport Index CSV dataset covering 199 countries
- **Report**: Bootstrap-powered HTML with destination cards, price breakdowns, and direct Google Flights links

## Requirements

- Python 3.12+
- Firefox browser (for cookie extraction)
- [Playwright](https://playwright.dev/python/) (fallback captcha solving)

## Project Structure

```
flight_finder/
├── main.py                  # Entry point
├── flight_search.py         # Skyscanner API search (countries → cities)
├── visa_rules.py            # Visa feasibility checker
├── html_report.py           # HTML report generator
├── cookie_fetcher.py        # Skyscanner cookie management
├── passport-index-data.csv  # Visa requirements dataset
└── requirements.txt         # Python dependencies
```

## License

MIT
