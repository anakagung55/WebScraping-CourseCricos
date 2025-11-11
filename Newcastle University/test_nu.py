from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import re, time

# === CONFIG ===
INPUT_FILE = "handbook.xlsx"
OUTPUT_FILE = "newcastle_handbook_bycode.sql"
BASE = "https://handbook.newcastle.edu.au/program/2025/"
HEADLESS = True
WAIT_AFTER_LOAD = 4000

# === HELPERS ===
def clean_html(html):
    return re.sub(r"\s+", " ", html.strip().replace("'", "''"))

def get_text(soup, selector):
    tag = soup.select_one(selector)
    return tag.get_text(" ", strip=True) if tag else ""

def extract_section(soup, id_pattern):
    div = soup.find("div", id=re.compile(id_pattern, re.I))
    if div:
        ps = div.find_all("p")
        if ps:
            return "".join(str(p) for p in ps)
    return ""

def extract_admission_and_english(soup):
    html_parts = []
    adm = soup.find("div", id=re.compile("Admissionrequirements", re.I))
    if adm:
        body = adm.find(attrs={"class": re.compile("CardBody")})
        if body:
            html_parts.append(str(body))
    eng = soup.find("div", id=re.compile("Englishlanguagerequirements", re.I))
    if eng:
        html_parts.append(str(eng))
    return "".join(html_parts)

def get_attr_value_by_header(soup, header_regex):
    for h3 in soup.find_all("h3"):
        title = h3.get_text(strip=True)
        if re.search(header_regex, title, flags=re.I):
            parent = h3.find_parent(attrs={"class": re.compile("AttrContainer")})
            if parent:
                val_div = parent.find("div", class_=re.compile("css-19qn38w"))
                if val_div:
                    return val_div.get_text(strip=True)
    return ""

def generate_sql(data):
    return f"""UPDATE courses SET
    course_description = '{data["course_description"]}',
    onshore_tuition_fee = '',
    offshore_tuition_fee = '',
    entry_requirements = '{data["entry_requirements"]}',
    total_course_duration = '{data["total_course_duration"]}',
    apply_form = ''
    WHERE cricos_course_code = '{data["cricos_course_code"]}';\n\n"""

# === MAIN SCRAPER ===
def scrape_program(page, code, name):
    url = f"{BASE}{code}"
    print(f"\n→ Scraping {url}")
    data = {
        "course_name": name,
        "cricos_course_code": "",
        "course_description": "",
        "total_course_duration": "",
        "entry_requirements": "",
        "apply_form": link
    }
    try:
        page.goto(url, timeout=60000)
        page.wait_for_timeout(WAIT_AFTER_LOAD)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Description
        desc = extract_section(soup, "^Description$")
        data["course_description"] = clean_html(desc)

        # Duration
        duration = get_attr_value_by_header(soup, r"Full time duration")
        if duration:
            duration = re.sub(r"[^\d]", "", duration)
            data["total_course_duration"] = f"{duration} years" if duration else ""

        # CRICOS code
        cricos = get_attr_value_by_header(soup, r"CRICOS code")
        data["cricos_course_code"] = cricos.strip()

        # Entry + English
        entry = extract_admission_and_english(soup)
        data["entry_requirements"] = clean_html(entry)

        print(f"✅ Success: {name} ({code})")
        return data
    except Exception as e:
        print(f"⚠️ Failed {name}: {e}")
        return None

def main():
    df = pd.read_excel(INPUT_FILE)
    print(f"📄 Loaded {len(df)} programs from {INPUT_FILE}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for i, row in enumerate(df.itertuples(), start=1):
                raw = str(row.data)
                parts = raw.split(" ", 1)
                if len(parts) < 2:
                    continue
                code, name = parts[0], parts[1]

                print(f"[{i}/{len(df)}] {code} - {name}")
                result = scrape_program(page, code, name)
                if result:
                    f.write(generate_sql(result))
                time.sleep(1)

        browser.close()

    print(f"\n🎉 Done! SQL saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
