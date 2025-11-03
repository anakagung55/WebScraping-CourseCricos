from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re, time

INPUT_FILE = "Newcastle.txt"
BASE = "https://www.newcastle.edu.au/degrees/"
OUTPUT_FILE = "newcastle_update.sql"

def parse_courses(file_path):
    courses = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) == 2:
                cricos, name = parts
                courses.append((cricos.strip(), name.strip()))
    return courses


def scrape_course(page, cricos, name):
    slug = (
        name.lower()
        .replace(" ", "-")
        .replace("(", "")
        .replace(")", "")
        .replace("/", "")
        .replace("&", "and")
    )
    url = f"{BASE}{slug}"
    print(f"\n→ Scraping {url}")

    data = {
        "cricos_code": cricos,
        "course_name": name,
        "course_description": "",
        "offshore_tuition_fee": "",
        "onshore_tuition_fee": "",
        "entry_requirements": "",
        "total_course_duration": "",
        "apply_form": ""
    }

    try:
        page.goto(url, timeout=90000, wait_until="domcontentloaded")
        page.wait_for_timeout(7000)  # tunggu JS render

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        wrapper = soup.find("div", class_="w65")
        if wrapper:
            ps = wrapper.find_all("p")
            if ps:
                desc = " ".join(p.get_text(" ", strip=True) for p in ps)
                data["course_description"] = desc.replace("'", "''")

        fee_tag = soup.select_one("span.degree-international-fee")
        if fee_tag:
            fee_text = fee_tag.get_text(strip=True)
            data["offshore_tuition_fee"] = re.sub(r"[^\d]", "", fee_text)

        entry_block = soup.select_one("p.admission-info-mid")
        if entry_block:
            data["entry_requirements"] = entry_block.get_text(" ", strip=True).replace("'", "''")

        dur_tag = soup.select_one("span.degree-full-time-duration")
        if dur_tag:
            data["total_course_duration"] = dur_tag.get_text(strip=True)

        apply_btn = soup.select_one("a.international-apply-button")
        if apply_btn:
            data["apply_form"] = apply_btn.get("href")

        print(f"✅ Success: {name}")

    except Exception as e:
        print(f"⚠️ Failed to load {name}: {e}")

    return data


def generate_sql(d):
    return f"""UPDATE courses SET
    course_description = '{d["course_description"]}',
    onshore_tuition_fee = '{d["onshore_tuition_fee"]}',
    offshore_tuition_fee = '{d["offshore_tuition_fee"]}',
    entry_requirements = '{d["entry_requirements"]}',
    total_course_duration = '{d["total_course_duration"]}',
    apply_form = '{d["apply_form"]}'
WHERE cricos_code = '{d["cricos_code"]}';\n\n"""


def main():
    courses = parse_courses(INPUT_FILE)
    print(f"📄 Loaded {len(courses)} courses from {INPUT_FILE}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for i, (cricos, name) in enumerate(courses, start=1):
                print(f"\n[{i}/{len(courses)}] {name} ({cricos})")
                data = scrape_course(page, cricos, name)
                f.write(generate_sql(data))
                time.sleep(2)

        browser.close()
    print(f"\n🎉 Done! SQL saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
