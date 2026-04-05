"""
Get Skyscanner cookies — from Firefox profile or via manual captcha solve.

Strategy:
  1. Try Firefox cookies from user's real browser profile
  2. If that fails (blocked), open browser for user to solve captcha manually
"""

import os
import shutil
import sqlite3
import time

COOKIE_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")
MAX_AGE_SECONDS = 20 * 60

# Firefox profile that has Skyscanner cookies
FIREFOX_PROFILES_DIR = os.path.expanduser("~/Library/Application Support/Firefox/Profiles/")


def cookies_are_fresh() -> bool:
    if not os.path.exists(COOKIE_FILE):
        return False
    age = time.time() - os.path.getmtime(COOKIE_FILE)
    return age < MAX_AGE_SECONDS


def _get_firefox_profile() -> str | None:
    """Find the Firefox profile that has Skyscanner cookies."""
    if not os.path.exists(FIREFOX_PROFILES_DIR):
        return None

    for profile in os.listdir(FIREFOX_PROFILES_DIR):
        cookies_db = os.path.join(FIREFOX_PROFILES_DIR, profile, "cookies.sqlite")
        if not os.path.exists(cookies_db):
            continue
        try:
            tmp_db = "/tmp/ff_cookies_check.sqlite"
            shutil.copy2(cookies_db, tmp_db)
            conn = sqlite3.connect(tmp_db)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM moz_cookies WHERE host LIKE '%skyscanner%'")
            count = c.fetchone()[0]
            conn.close()
            if count > 0:
                return profile
        except Exception:
            continue
    return None


def _extract_firefox_cookies() -> str:
    """Extract Skyscanner cookies from Firefox profile."""
    profile = _get_firefox_profile()
    if not profile:
        return ""

    cookies_db = os.path.join(FIREFOX_PROFILES_DIR, profile, "cookies.sqlite")
    tmp_db = "/tmp/ff_cookies.sqlite"
    shutil.copy2(cookies_db, tmp_db)

    conn = sqlite3.connect(tmp_db)
    c = conn.cursor()
    c.execute("SELECT name, value FROM moz_cookies WHERE host LIKE '%skyscanner%'")
    rows = c.fetchall()
    conn.close()

    if not rows:
        return ""

    cookie_str = "; ".join(f"{name}={value}" for name, value in rows)
    print(f"  [Extracted {len(rows)} cookies from Firefox]")
    return cookie_str


def _test_cookies(cookie_str: str) -> bool:
    """Test if cookies work by making a simple API call."""
    import json
    import subprocess

    body = json.dumps({
        "cabinClass": "ECONOMY", "childAges": [], "adults": 1,
        "legs": [
            {"legOrigin": {"@type": "entity", "entityId": "27542903"}, "legDestination": {"@type": "everywhere"}, "dates": {"@type": "month", "year": 2026, "month": 5}},
            {"legOrigin": {"@type": "everywhere"}, "legDestination": {"@type": "entity", "entityId": "27542903"}, "dates": {"@type": "month", "year": 2026, "month": 5}},
        ],
        "options": {"fareAttributes": {"selectedFareAttributes": []}},
    })

    cmd = [
        "curl", "-s", "--compressed", "-X", "POST",
        "https://www.skyscanner.com.tr/g/radar/api/v2/web-unified-search/",
        "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:149.0) Gecko/20100101 Firefox/149.0",
        "-H", "Accept: application/json",
        "-H", "Content-Type: application/json",
        "-H", "X-Skyscanner-ChannelId: banana",
        "-H", "X-Skyscanner-Market: TR",
        "-H", "X-Skyscanner-Locale: en-US",
        "-H", "X-Skyscanner-Currency: USD",
        "-H", "X-Skyscanner-DeviceDetection-IsMobile: false",
        "-H", "X-Skyscanner-DeviceDetection-IsTablet: false",
        "-H", "X-Skyscanner-Skip-Accommodation-Carhire: true",
        "-H", "X-Radar-Combined-Explore-Unfocused-Locations-Use-Real-Data: 1",
        "-H", "X-Radar-Combined-Explore-Generic-Results: 1",
        "-H", "X-Skyscanner-Combined-Results-Hotel-Polling: true",
        "-H", "Origin: https://www.skyscanner.com.tr",
        "-H", "Referer: https://www.skyscanner.com.tr/",
        "-H", f"Cookie: {cookie_str}",
        "--data-raw", body,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        if data.get("reason") == "blocked" or data.get("status") == "400":
            return False
        return True
    except Exception:
        return False


def fetch_cookies_with_captcha() -> str:
    """Open browser for user to solve captcha, then extract cookies."""
    from playwright.sync_api import sync_playwright

    print("  [Opening browser — please solve the captcha if it appears...]")
    print("  [After the Skyscanner page loads fully, cookies will be captured automatically]")

    pw = sync_playwright().start()
    browser = pw.firefox.launch(headless=False)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:149.0) Gecko/20100101 Firefox/149.0",
        locale="en-US",
        viewport={"width": 1280, "height": 900},
    )

    page = context.new_page()

    # Go to Skyscanner — might show captcha
    page.goto("https://www.skyscanner.com.tr/", wait_until="load", timeout=60000)

    # Wait for user to solve captcha — poll until page has real content
    max_wait = 120  # 2 minutes for user to solve captcha
    start = time.time()
    while time.time() - start < max_wait:
        page.wait_for_timeout(2000)
        content = page.content()
        title = page.title()

        # Check if captcha is gone and real page loaded
        has_captcha = "px-captcha" in content.lower()
        has_real_content = "skyscanner" in title.lower() and not has_captcha

        if has_real_content:
            print("  [Captcha solved! Loading explore page...]")
            break
    else:
        print("  [Timeout waiting for captcha — using whatever cookies we have]")

    # Navigate to explore page to get full API cookies
    try:
        page.goto(
            "https://www.skyscanner.com.tr/transport/flights-from/ista/?adultsv2=1&cabinclass=economy&rtn=1",
            wait_until="load",
            timeout=45000,
        )
        page.wait_for_timeout(8000)
    except Exception:
        pass

    # Extract cookies
    cookies = context.cookies()
    browser.close()
    pw.stop()

    if not cookies:
        print("  [No cookies captured]")
        return ""

    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    print(f"  [Got {len(cookies)} cookies after captcha]")
    return cookie_str


def fetch_cookies() -> str:
    """Try Firefox cookies first, fall back to manual captcha solve."""
    # Step 1: Try Firefox cookies
    print("  [Checking Firefox for Skyscanner cookies...]")
    cookie_str = _extract_firefox_cookies()

    if cookie_str:
        print("  [Testing Firefox cookies...]")
        if _test_cookies(cookie_str):
            print("  [Firefox cookies work!]")
            with open(COOKIE_FILE, "w") as f:
                f.write(cookie_str)
            return cookie_str
        else:
            print("  [Firefox cookies expired/blocked]")

    # Step 2: Open browser for captcha
    cookie_str = fetch_cookies_with_captcha()

    if cookie_str:
        with open(COOKIE_FILE, "w") as f:
            f.write(cookie_str)

        if _test_cookies(cookie_str):
            print("  [Cookies work after captcha!]")
            return cookie_str
        else:
            print("  [Warning: cookies still blocked after captcha]")

    return cookie_str


def get_cookies() -> str:
    """Get cookies — from cache if fresh, otherwise fetch new ones."""
    if cookies_are_fresh():
        with open(COOKIE_FILE) as f:
            return f.read().strip()

    try:
        return fetch_cookies()
    except Exception as e:
        print(f"  [Cookie fetch failed: {e}]")
        if os.path.exists(COOKIE_FILE):
            print("  [Using existing cookies.txt as fallback]")
            with open(COOKIE_FILE) as f:
                return f.read().strip()
        return ""
