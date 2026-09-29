"""
Scrapes a random Ghazal (in Urdu script) from a random poet on Rekhta's
top-read-poets page: https://www.rekhta.org/poets/top-read-poets

Flow:
    1. Collect every poet listed on the top-read-poets page (it's paginated
       behind an AJAX "load more" endpoint).
    2. Pick one poet at random.
    3. From that poet's page, collect the 5 Ghazals shown in the "Ghazal"
       section (no "See All" expansion).
    4. Pick one Ghazal at random.
    5. Open the Ghazal in its Urdu-script mode (?lang=ur) and pull out the
       poem text. This page renders the poem client-side, so a real browser
       (Playwright) is used instead of a plain HTTP request.
"""

import random
import re

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://www.rekhta.org"
POETS_URL = f"{BASE_URL}/poets/top-read-poets"
POET_COLLECTION_AJAX_URL = f"{BASE_URL}/PoetCollection"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

MAX_POET_LIST_PAGES = 10
MAX_POET_ATTEMPTS = 10


def _make_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    })
    return session


def _extract_poets(html, poets):
    soup = BeautifulSoup(html, "html.parser")
    for item in soup.find_all("div", class_="nwPoetListingItem"):
        link = item.select_one(".poetNameDatePlace a[href]")
        if not link:
            continue
        match = re.search(r"/poets/([a-zA-Z0-9-]+)", link["href"])
        if not match:
            continue
        slug = match.group(1)
        name = link.get_text(strip=True)
        poets[slug] = (name, f"{BASE_URL}/poets/{slug}")


def get_all_poets(session):
    """Returns a list of (poet_name, poet_url) tuples for every poet on the
    top-read-poets listing, paginating through the AJAX "load more" endpoint."""
    poets = {}

    response = session.get(POETS_URL, timeout=15)
    response.raise_for_status()
    _extract_poets(response.text, poets)

    for page_number in range(2, MAX_POET_LIST_PAGES + 1):
        params = {
            "lang": 1,
            "pageNumber": page_number,
            "Info": "poetCollections",
            "SEO_Slug": "top-read-poets",
        }
        response = session.get(
            POET_COLLECTION_AJAX_URL,
            params=params,
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": POETS_URL},
            timeout=15,
        )
        if response.status_code != 200 or not response.text.strip():
            break

        count_before = len(poets)
        _extract_poets(response.text, poets)
        if len(poets) == count_before:
            break

    return list(poets.values())


def get_ghazals_for_poet(session, poet_url):
    """Returns the (up to 5) Ghazals shown on a poet's page as
    (title, ghazal_url) tuples."""
    response = session.get(poet_url, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    ghazal_section = soup.find("div", class_="poetGhzl")
    if not ghazal_section:
        return []

    ghazals = {}
    for link in ghazal_section.find_all("a", href=True):
        href = link["href"]
        if "/ghazals/" not in href:
            continue
        title_tag = link.find("h3")
        if not title_tag:
            continue
        ghazals[href] = title_tag.get_text(strip=True)

    return list(ghazals.items())


def fetch_ghazal_in_urdu(ghazal_url):
    """Loads the Ghazal's Urdu-script page in a headless browser (the poem
    body is rendered client-side) and returns its couplets plus titles.
    Returns None if the page fails to load or never renders a poem
    (Rekhta has background network activity that can make "networkidle"
    unreliable, and occasional pages just fail to render in time)."""
    separator = "&" if "?" in ghazal_url else "?"
    urdu_url = f"{ghazal_url}{separator}lang=ur"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(urdu_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("div.pMC", timeout=20000, state="attached")
            page.wait_for_timeout(1500)
            html = page.content()
            browser.close()
    except PlaywrightTimeoutError:
        return None

    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h1")
    poet_name_tag = soup.find("h2")
    ghazal_title_ur = title_tag.get_text(strip=True) if title_tag else ""
    poet_name_ur = poet_name_tag.get_text(strip=True) if poet_name_tag else ""

    urdu_blocks = soup.find_all("div", class_="pMC", attrs={"data-roman": "off"})
    if not urdu_blocks:
        return None

    poem_block = urdu_blocks[-1]
    couplets = []
    for couplet_div in poem_block.find_all("div", class_="c"):
        lines = []
        for line_tag in couplet_div.find_all("p"):
            line_text = " ".join(line_tag.get_text(" ", strip=True).split())
            if line_text:
                lines.append(line_text)
        if lines:
            couplets.append(lines)

    if not couplets:
        return None

    return {
        "ghazal_title_ur": ghazal_title_ur,
        "poet_name_ur": poet_name_ur,
        "couplets": couplets,
    }


def get_random_ghazal():
    """Picks a random poet and a random Ghazal of theirs, and returns the
    full Urdu poem along with some metadata."""
    session = _make_session()
    poets = get_all_poets(session)
    if not poets:
        raise RuntimeError("Could not find any poets on the top-read-poets page.")

    random.shuffle(poets)

    for poet_name, poet_url in poets[:MAX_POET_ATTEMPTS]:
        ghazals = get_ghazals_for_poet(session, poet_url)
        if not ghazals:
            continue

        ghazal_url, ghazal_title_en = random.choice(ghazals)
        poem = fetch_ghazal_in_urdu(ghazal_url)
        if not poem:
            continue

        return {
            "poet_name_en": poet_name,
            "poet_url": poet_url,
            "ghazal_title_en": ghazal_title_en,
            "ghazal_url": ghazal_url,
            **poem,
        }

    raise RuntimeError(
        f"Could not find a scrapable Ghazal after {MAX_POET_ATTEMPTS} poet attempts."
    )


def print_ghazal(ghazal):
    print(f"{ghazal['poet_name_ur']}  ({ghazal['poet_name_en']})")
    print(f"{ghazal['ghazal_title_ur']}  ({ghazal['ghazal_title_en']})")
    print(f"Source: {ghazal['ghazal_url']}")
    print()
    for couplet in ghazal["couplets"]:
        for line in couplet:
            print(line)
        print()


if __name__ == "__main__":
    print_ghazal(get_random_ghazal())
