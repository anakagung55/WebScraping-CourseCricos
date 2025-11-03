import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

# === EXTRACT FEE VALUE ===
def extract_fee_value(html: str) -> str:
    m = re.search(r"\$([\d,]+)", html)
    return m.group(1).replace(",", "") if m else ""

# === SCRAPER PER COURSE ===
async def scrape_csu_course(page, url, duration):
    data = {
        "url": url,
        "course_description": "",
        "total_course_duration": duration,
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "cricos_course_code": "",
        "apply_form": "https://study.csu.edu.au/international/apply"
    }

    try:
        print(f"🌐 Scraping {url} ...")
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === DESCRIPTION ===
        desc_div = soup.select_one("div.course-overview, div.populate-course-overview, div#rmjs-1")
        if desc_div:
            data["course_description"] = clean_html(str(desc_div))
        else:
            print("⚠️ No description found")

        # === FEE ===
        fee_div = soup.select_one("div.key-info-content.populate-indicative-fees, div.populate-fees, section#fees")
        if fee_div:
            data["offshore_tuition_fee"] = extract_fee_value(fee_div.get_text())
        else:
            print("⚠️ No fee section found")

        # === ENTRY REQUIREMENTS ===
        entry_section = soup.select_one("section#entry-requirements, div#entry-requirements, div.populate-entry-requirements")
        if entry_section:
            data["entry_requirements"] = clean_html(str(entry_section))
        else:
            print("⚠️ No entry requirements found")

        # === CRICOS ===
        cricos_span = soup.select_one("div.show-international.cricos-code span.populate-cricos-code, span.populate-cricos-code")
        if cricos_span:
            data["cricos_course_code"] = cricos_span.get_text(strip=True)
        else:
            print("⚠️ No CRICOS code found")

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")

    return data


# === MAIN LOOP ===
async def main():
    df = pd.read_excel("study_csu.xlsx")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i, row in df.iterrows():
            title = str(row.get("title", ""))
            url = str(row.get("url", ""))
            duration = str(row.get("duration", ""))
            print(f"\n[{i+1}/{len(df)}] {title}")
            course_data = await scrape_csu_course(page, url, duration)
            results.append(course_data)

        await browser.close()

    # === ESCAPE FUNCTION UNTUK SQL SAFE ===
    def escape_sql(text: str) -> str:
        if not text:
            return ""
        return text.replace("'", "''")

    # === OUTPUT SQL FILE ===
    sql_lines = []
    for d in results:
        sql = f"""UPDATE courses SET
    course_description = '{escape_sql(d["course_description"])}',
    total_course_duration = '{escape_sql(d["total_course_duration"])}',
    offshore_tuition_fee = '{escape_sql(d["offshore_tuition_fee"])}',
    entry_requirements = '{escape_sql(d["entry_requirements"])}',
    apply_form = '{escape_sql(d["apply_form"])}'
WHERE cricos_course_code = '{escape_sql(d["cricos_course_code"])}';"""
        sql_lines.append(sql)

    with open("csu_update.sql", "w", encoding="utf-8") as f:
        f.write("\n\n".join(sql_lines))

    print("\n✅ Done! SQL file saved as csu_update.sql")


# === RUN ===
asyncio.run(main())
