import requests
from bs4 import BeautifulSoup
import re
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===================== CONFIG =====================
COURSES_FILE = "Courses - ACU.txt"
BASE = "https://www.acu.edu.au/course/"
OUTPUT_FILE = "acu_courses_update.sql"
REQUEST_TIMEOUT = 60
DELAY_BETWEEN_REQUESTS = 3
# ==================================================

# setup session + retry
session = requests.Session()
retries = Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
session.mount("https://", HTTPAdapter(max_retries=retries))

def extract_number(text):
    match = re.search(r'\$?([\d,]+)', text)
    return match.group(1).replace(',', '') if match else ''

def clean_html(html):
    """bersihkan whitespace tanpa menghapus tag HTML"""
    return re.sub(r'\s+', ' ', html.strip().replace("'", "''"))

def scrape_course(course_name):
    slug = (
        course_name.lower()
        .replace(" ", "-")
        .replace("(", "")
        .replace(")", "")
        .replace("/", "")
        .replace("’", "")
    )
    onshore_url = f"{BASE}{slug}"
    offshore_url = f"{BASE}{slug}?type=International"

    data = {
        "onshore_tuition_fee": "",
        "offshore_tuition_fee": "",
        "total_course_duration": "",
        "course_description": "",
        "entry_requirements": "",
        "course_duration_per_week": "",
        "apply_form": "",
    }

    try:
        # ----------- ON SHORE -----------
        r = session.get(onshore_url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            print(f"⚠️ Skip {course_name}: page not found ({r.status_code})")
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        # Description (HTML)
        desc_block = soup.find("div", {"id": "overview-description"})
        if desc_block:
            ps = desc_block.find_all("p")
            if ps:
                html_content = "".join([str(p) for p in ps])
                data["course_description"] = clean_html(html_content)

        # Duration (e.g. "2 years")
        dur_tag = soup.find("dd", string=re.compile("year", re.I))
        if dur_tag:
            m = re.search(r"(\d+\s*years?)", dur_tag.text, re.I)
            data["total_course_duration"] = m.group(1) if m else ""

        # Fee (onshore)
        fee_tag = soup.find("a", href="#feeaccordion")
        if fee_tag:
            data["onshore_tuition_fee"] = extract_number(fee_tag.text)

        # Apply form
        apply_link = None
        reg_div = soup.find("div", class_="banner-button-wrap banner-register")
        if reg_div and reg_div.find("a", href=True):
            apply_link = reg_div.find("a")["href"]
        if not apply_link:
            apply_btn = soup.find("button", {"data-target": "#applynowmodal"})
            if apply_btn:
                apply_link = "Apply form (modal)"
        data["apply_form"] = apply_link or ""

        # Entry requirements (h2 filter)
        entry_divs = soup.find_all("div", class_="col-md-12 side-accordion--multi")
        target_div = None
        for div in entry_divs:
            h2 = div.find("h2")
            if h2 and "entry requirements" in h2.get_text(strip=True).lower():
                target_div = div
                break
        if target_div:
            data["entry_requirements"] = clean_html(str(target_div))

        # ----------- OFF SHORE -----------
        r2 = session.get(offshore_url, timeout=REQUEST_TIMEOUT)
        if r2.status_code == 200:
            soup2 = BeautifulSoup(r2.text, "html.parser")
            fee_dd = soup2.find("dd", string=re.compile(r"^\$[\d,]+", re.I))
            if fee_dd:
                data["offshore_tuition_fee"] = extract_number(fee_dd.text)

        return data

    except Exception as e:
        print(f"❌ Error scraping {course_name}: {e}")
        return None


def generate_update_query(cricos_code, course_data):
    q = f"""UPDATE courses SET
    course_description = '{course_data["course_description"]}',
    offshore_tuition_fee = '{course_data["offshore_tuition_fee"]}',
    onshore_tuition_fee = '{course_data["onshore_tuition_fee"]}',
    entry_requirements = '{course_data["entry_requirements"]}',
    total_course_duration = '{course_data["total_course_duration"]}',
    course_duration_per_week = '{course_data["course_duration_per_week"]}',
    apply_form = '{course_data["apply_form"]}'
    WHERE cricos_course_code = '{cricos_code}';\n\n"""
    return q


def main():
    # Baca file daftar course
    with open(COURSES_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    pairs = []
    for line in lines:
        if "\t" in line:
            code, name = line.split("\t", 1)
            pairs.append((code.strip(), name.strip()))

    # scraping tiap course
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for idx, (code, name) in enumerate(pairs, start=1):
            print(f"\n[{idx}/{len(pairs)}] Scraping: {name} ({code})")
            data = scrape_course(name)
            if data:
                query = generate_update_query(code, data)
                f.write(query)
                print(f"✅ Success: {name}")
            else:
                print(f"⚠️ Failed: {name}")
            time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"\n🎉 Finished! Queries saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
