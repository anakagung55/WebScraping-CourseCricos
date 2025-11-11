from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import time, os

# === KONFIGURASI ===
INPUT_FILE = "Western Sydney University/wsu_course_links.xlsx"
OUTPUT_SQL = "wsu_update_courses.sql"
SAVE_INTERVAL = 10  # Simpan setiap 10 course

# === BACA LINK (pastikan ada kolom course_url) ===
df = pd.read_excel(INPUT_FILE)

# pastikan nama kolomnya "course_url" — jika beda, ubah di sini
if "course_url" not in df.columns:
    raise ValueError("❌ Kolom 'course_url' tidak ditemukan di file Excel!")

links = df["course_url"].dropna().tolist()

sql_results = []

def clean_fee(text):
    """Ambil hanya angka dari string fee"""
    return "".join(ch for ch in text if ch.isdigit())

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    for i, url in enumerate(links, start=1):
        print(f"[{i}/{len(links)}] Fetching: {url}")
        try:
            page.goto(url, timeout=60000)
            time.sleep(3)
            soup = BeautifulSoup(page.content(), "html.parser")

            # === DESCRIPTION ===
            desc_div = soup.find("div", class_="course_heading_description")
            course_description = str(desc_div) if desc_div else ""

            # === DURATION ===
            dur_div = soup.find("div", class_="course_duration_info_box")
            total_course_duration = dur_div.get_text(strip=True) if dur_div else ""

            # === OFFSHORE FEE (INTERNATIONAL) ===
            offshore_fee = ""
            fee_tag = soup.find("p", class_="cmp-fees-scholarship-section-form-para-international")
            if fee_tag:
                text = fee_tag.get_text(strip=True)
                offshore_fee = clean_fee(text)

            # === ONSHORE FEE (DOMESTIC) ===
            onshore_fee = ""
            dom_tag = soup.find("p", class_="cmp-fees-scholarship-section-form-para-domestic")
            if dom_tag:
                text = dom_tag.get_text(strip=True)
                onshore_fee = clean_fee(text)

            # === CRICOS CODE ===
            cricos_code = ""
            cricos_tag = soup.find("p", class_="course_info_cricos_code")
            if cricos_tag:
                text = cricos_tag.get_text(strip=True)
                if "CRICOS" in text:
                    cricos_code = text.split(":")[-1].strip()

            # Jika CRICOS kosong → skip
            if not cricos_code:
                print("⚠️ Skipped (no CRICOS):", url)
                continue

            # === ENTRY REQUIREMENTS ===
            entry_sections = soup.find_all("div", class_="component component--wysiwyg aem-GridColumn aem-GridColumn--default--12")
            entry_html = "".join(str(div) for div in entry_sections) if entry_sections else ""

            # === APPLY FORM (langsung dari link course) ===
            apply_form = url

            # === GENERATE SQL ===
            sql = f"""
UPDATE courses SET
    course_description = {repr(course_description)},
    total_course_duration = {repr(total_course_duration)},
    onshore_tuition_fee = {repr(onshore_fee)},
    offshore_tuition_fee = {repr(offshore_fee)},
    entry_requirements = {repr(entry_html)},
    apply_form = {repr(apply_form)},
    created_at = NOW(),
    updated_at = NOW()
WHERE cricos_course_code = {repr(cricos_code)};
"""

            sql_results.append(sql)
            print(f"✅ Success: {cricos_code}")

            # === SIMPAN SETIAP 10 COURSE ===
            if i % SAVE_INTERVAL == 0:
                with open(OUTPUT_SQL, "a", encoding="utf-8") as f:
                    f.write("\n".join(sql_results) + "\n")
                sql_results = []
                print(f"💾 Saved progress up to course {i}")

        except Exception as e:
            print(f"❌ Error fetching {url}: {e}")
            continue

    # === SIMPAN SISA DATA ===
    if sql_results:
        with open(OUTPUT_SQL, "a", encoding="utf-8") as f:
            f.write("\n".join(sql_results) + "\n")

    browser.close()

print("\n🎯 Done! All SQL updates saved to:", OUTPUT_SQL)
