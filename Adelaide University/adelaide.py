from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd, re, os

# === KONFIGURASI ===
INPUT_FILE = "Book1.xlsx"
OUTPUT_FILE = "adelaide_update.sql"
APPLY_FORM_URL = "https://adelaideuni.edu.au/study/#undergraduate"
BATCH_SIZE = 5  # Simpan tiap 50 record

# === BACA FILE EXCEL ===
df = pd.read_excel(INPUT_FILE)
base_links = df.iloc[:, 0].dropna().tolist()

def get_course_data(page, url):
    print(f"→ Scraping: {url}")
    try:
        page.goto(url, timeout=60000)
        page.wait_for_load_state("domcontentloaded")
    except Exception as e:
        print(f"⚠️ Gagal buka {url}: {e}")
        return None

    soup = BeautifulSoup(page.content(), "html.parser")

    data = {
        "course_description": "",
        "onshore_tuition_fee": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "total_course_duration": "",
        "apply_form": APPLY_FORM_URL,
        "cricos_course_code": ""
    }

    # === Overview ===
    overview = soup.find("h3", string="Overview")
    if overview:
        paragraphs = []
        for tag in overview.find_all_next():
            if tag.name == "h3" and tag.get_text(strip=True) != "Overview":
                break
            if tag.name == "p":
                paragraphs.append(str(tag))
        data["course_description"] = "".join(paragraphs)

    # === Entry Requirements ===
    block = soup.select_one("div.block-content-wrapper")
    if block:
        data["entry_requirements"] = str(block)

    # === Duration ===
    dur_span = soup.find("span", string=re.compile("year", re.I))
    if dur_span:
        data["total_course_duration"] = dur_span.get_text(strip=True)

    # === Tuition Fee (OFFSHORE only di /int/) ===
    data["onshore_tuition_fee"] = ""  # kosongkan domestic semua sesuai request
    if "/int/" in url:
        fee_span = soup.select_one("div.degree-details-content-section-subtitle span")
        fee_value = ""
        if fee_span and "$" in fee_span.get_text():
            fee_value = fee_span.get_text(strip=True)
        else:
            # fallback cari teks mengandung $
            text_with_dollar = soup.find(string=re.compile(r"\$[0-9,]+"))
            if text_with_dollar:
                fee_value = text_with_dollar.strip()
        if fee_value:
            data["offshore_tuition_fee"] = fee_value

    # === CRICOS Code (perbaikan) ===
    cricos = ""
    label = soup.find("span", string=re.compile(r"^\s*CRICOS code\s*$", re.I))
    if label:
        container = label.find_parent(class_=re.compile(r"degree-details-content-section-icon-list-top"))
        if container:
            val = container.select_one(".degree-details-content-section-subtitle span")
            if val:
                cricos = val.get_text(strip=True)
    if not cricos:
        icon_block = soup.find("div", class_=re.compile(r"degree-details-content-section-icon"))
        if icon_block and icon_block.find(string=re.compile(r"CRICOS code", re.I)):
            val = icon_block.select_one(".degree-details-content-section-subtitle span")
            if val:
                cricos = val.get_text(strip=True)
    if not cricos:
        m = soup.find(string=re.compile(r"\b\d{5,6}[A-Za-z]\b"))
        if m:
            cricos = m.strip()
    data["cricos_course_code"] = cricos

    return data

def save_progress(sql_lines, count):
    """Simpan batch SQL ke file"""
    if not sql_lines:
        return
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.writelines(sql_lines)
    print(f"💾 Progress disimpan! ({count} records)\n")


# === MAIN SCRAPER ===
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Block resource gak penting
    page.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in ["image", "font", "media", "stylesheet"]
        else route.continue_()
    )

    sql_lines = []
    counter = 0

    print("\n🚀 Mulai scraping University of Adelaide...\n")

    for base_url in base_links:
        base_url = str(base_url).strip()
        if not base_url.startswith("http"):
            print(f"⚠️ Skip invalid URL: {base_url}")
            continue

        dom_url = base_url.rstrip("/") + "/dom/"
        int_url = base_url.rstrip("/") + "/int/"

        # scrape domestic dan international
        data_dom = get_course_data(page, dom_url)
        data_int = get_course_data(page, int_url)

        if not data_dom and not data_int:
            continue

        # ambil data prioritas dari international
        course_description = (data_int or {}).get("course_description") or (data_dom or {}).get("course_description")
        entry_req = (data_int or {}).get("entry_requirements") or (data_dom or {}).get("entry_requirements")
        total_duration = (data_int or {}).get("total_course_duration") or (data_dom or {}).get("total_course_duration")
        offshore_fee = (data_int or {}).get("offshore_tuition_fee", "")
        cricos = (data_int or {}).get("cricos_course_code", "")

        if not cricos:
            print(f"⚠️ CRICOS code not found for {base_url}, skipped.\n")
            continue

        sql = f"""
UPDATE courses SET
    course_description = '{course_description.replace("'", "''")}',
    onshore_tuition_fee = '',
    offshore_tuition_fee = '{offshore_fee}',
    entry_requirements = '{entry_req.replace("'", "''")}',
    total_course_duration = '{total_duration}',
    apply_form = '{APPLY_FORM_URL}'
WHERE cricos_course_code = '{cricos}';
"""
        sql_lines.append(sql)
        counter += 1
        print(f"✅ Added SQL for {cricos}")

        # Simpan tiap batch
        if counter % BATCH_SIZE == 0:
            save_progress(sql_lines, counter)
            sql_lines = []

    # Simpan sisa terakhir
    save_progress(sql_lines, counter)
    browser.close()

print("\n🎉 Selesai! File SQL tersimpan di:", OUTPUT_FILE)
