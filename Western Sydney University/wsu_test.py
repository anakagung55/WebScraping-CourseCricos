from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time

url = "https://www.westernsydney.edu.au/future/study/courses/undergraduate/bachelor-of-nursing"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, timeout=60000)
    time.sleep(3)

    soup = BeautifulSoup(page.content(), "html.parser")

    # === Description ===
    desc_div = soup.find("div", class_="cmp-course__overview__two-column")
    course_description = str(desc_div) if desc_div else ""

    # === Duration ===
    dur_div = soup.find("div", class_="course_duration_info_box")
    total_course_duration = dur_div.get_text(strip=True) if dur_div else ""

    # === Offshore Fee (international) ===
    offshore_fee = ""
    fee_tag = soup.find("p", class_="cmp-fees-scholarship-section-form-para-international")

    if fee_tag:
        text = fee_tag.get_text(strip=True)
        # Ambil hanya angka dari string
        digits = "".join(ch for ch in text if ch.isdigit())
        offshore_fee = digits if digits else ""

    # === CRICOS ===
    cricos_tag = soup.find("p", class_="course_info_cricos_code")
    cricos_code = ""
    if cricos_tag:
        text = cricos_tag.get_text(strip=True)
        if "CRICOS" in text:
            cricos_code = text.split(":")[-1].strip()

    # === Entry Requirements ===
    entry_sections = soup.find_all("div", class_="component component--wysiwyg aem-GridColumn aem-GridColumn--default--12")
    entry_html = "".join(str(div) for div in entry_sections) if entry_sections else ""

    # === Apply Form ===
    apply_form = "http://apply.westernsydney.edu.au/"

    browser.close()

# === SQL Output ===
sql = f"""
UPDATE courses SET
    course_description = {repr(course_description)},
    total_course_duration = {repr(total_course_duration)},
    onshore_tuition_fee = '',
    offshore_tuition_fee = {repr(offshore_fee)},
    entry_requirements = {repr(entry_html)},
    apply_form = {repr(apply_form)}
WHERE cricos_course_code = {repr(cricos_code)};
"""

print(sql)
