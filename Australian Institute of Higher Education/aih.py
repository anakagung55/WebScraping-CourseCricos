import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

# === SCRAPE ENTRY REQUIREMENTS (HANYA SEKALI) ===
async def scrape_entry_requirements(browser):
    entry_url = "https://aih.edu.au/students/entry-requirements/international-students/"
    page = await browser.new_page()
    await page.goto(entry_url, timeout=90000)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    section = soup.select_one("section.vc_section.gray_boxrow.pb-65")
    entry_html = clean_html(str(section)) if section else ""
    await page.close()
    return entry_html

# === SCRAPE PER COURSE ===
async def scrape_course(url, browser, entry_html):
    data = {
        "url": url,
        "course_description": "",
        "cricos_course_code": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": entry_html,
        "apply_form": "https://aih.edu.au",
    }

    try:
        page = await browser.new_page()
        await page.goto(url, timeout=90000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # DESC
        desc = soup.select_one(".wpb_text_column.wpb_content_element.montserrat.subpagetext_p.container_1000 .wpb_wrapper")
        if desc:
            data["course_description"] = clean_html(str(desc))

        # CRICOS
        cricos_match = re.search(r"CRICOS Code:\s*([A-Z0-9]+)", html)
        if cricos_match:
            data["cricos_course_code"] = cricos_match.group(1)

        # === DURATION (cari angka + years + full time)
        duration_text = ""
        # Cari pola umum: 1 year full time, 3 years full time, etc
        match = re.search(r"(\d+\s*(term|terms|week|weeks|month|months|year|years|yr|yrs)\s*full\s*time)", html, re.IGNORECASE)
        if match:
            duration_text = match.group(1).strip()

        # Fallback: cari teks setelah kata "Duration:"
        if not duration_text:
            dur_match = re.search(r"Duration[:\s-]*([^<\n\r]+)", html, re.IGNORECASE)
            if dur_match:
                duration_text = dur_match.group(1).strip()

        data["total_course_duration"] = duration_text


        # FEE (ambil angka terbesar)
        fee_tags = soup.select("h2.keygreen_h2")
        if fee_tags:
            fees = []
            for tag in fee_tags:
                txt = tag.get_text(strip=True)
                num = re.sub(r"[^\d]", "", txt)
                if num.isdigit():
                    fees.append(int(num))
            if fees:
                data["offshore_tuition_fee"] = str(max(fees))

        await page.close()
    except Exception as e:
        print(f"❌ Error scraping {url}: {e}")
        await page.close()
    return data

# === MAIN ===
async def main():
    df = pd.read_excel("Australian Institute of Higher Education/aih.xlsx")  # kolom: title, url
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # 1️⃣ Ambil entry requirement global
        print("Scraping entry requirements (once)...")
        ENTRY_HTML = await scrape_entry_requirements(browser)

        # 2️⃣ Loop setiap course di Excel
        for idx, row in df.iterrows():
            url = str(row["url"]).strip()
            print(f"\n[{idx+1}/{len(df)}] Scraping: {url}")
            course = await scrape_course(url, browser, ENTRY_HTML)
            if course["cricos_course_code"]:
                results.append(course)
            else:
                print(f"⚠️ Skipped (no CRICOS): {url}")

        await browser.close()

    # 3️⃣ Output ke file SQL
    with open("aih_output.sql", "w", encoding="utf-8") as f:
        for d in results:
            f.write(f"""
UPDATE courses SET
    course_description = '{d["course_description"]}',
    total_course_duration = '{d["total_course_duration"]}',
    offshore_tuition_fee = '{d["offshore_tuition_fee"]}',
    entry_requirements = '{d["entry_requirements"]}',
    created_at = NOW(),
    updated_at = NOW(),
    apply_form = '{d["apply_form"]}'
WHERE cricos_course_code = '{d["cricos_course_code"]}';
""")

    print(f"\n✅ Selesai! {len(results)} course berhasil disimpan ke aih_output.sql")

asyncio.run(main())
