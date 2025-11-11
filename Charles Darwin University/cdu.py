import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from playwright.async_api import async_playwright

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    """Membersihkan whitespace dan escape tanda kutip SQL"""
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = html.replace("'", "''")
    return html.strip()

# === SANITIZE HTML ===
def sanitize_html(soup: BeautifulSoup) -> str:
    """Ubah <h1,h2,h3> ke <p style='font-weight:bold;'> dan hapus media tag"""
    for tag in soup.find_all(['img', 'svg', 'picture', 'iframe', 'video', 'source', 'button']):
        tag.decompose()

    for h in soup.find_all(['h1', 'h2', 'h3']):
        h.name = 'p'
        h['style'] = 'font-weight:bold;'

    return str(soup)

# === EXTRACT FEE VALUE ===
def extract_fee_value(html: str) -> str:
    m = re.search(r"\$([\d,]+)", html)
    return m.group(1).replace(",", "") if m else ""

# === SCRAPER PER COURSE ===
async def scrape_cdu_course(page, url, duration):
    data = {
        "url": url,
        "course_description": "",
        "total_course_duration": duration,
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "cricos_course_code": "",
        "apply_form": url,  # langsung ke URL course
    }

    print(f"🌐 Scraping {url} ...")
    try:
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === DESCRIPTION ===
        desc_div = soup.select_one("div#overview.section.rich-text")
        if desc_div:
            data["course_description"] = clean_html(sanitize_html(desc_div))

        # === FEE ===
        fee_p = soup.find(lambda tag: tag.name == "p" and "$" in tag.get_text())
        if fee_p:
            data["offshore_tuition_fee"] = extract_fee_value(fee_p.get_text())

        # === ENTRY REQUIREMENTS ===
        entry_div = soup.select_one("div#entry-requirements.section.rich-text")
        if entry_div:
            data["entry_requirements"] = clean_html(sanitize_html(entry_div))

        # === CRICOS CODE ===
        for div in soup.select("div.fable__cell.fable__value.align--right"):
            text = div.get_text(strip=True)
            if re.match(r"^\d{6,7}[A-Za-z]?$", text):
                data["cricos_course_code"] = text
                break

        print(f"✅ Done: {data['cricos_course_code']}")

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")

    return data


# === MAIN LOOP ===
async def main():
    df = pd.read_excel("Charles Darwin University/cdu.xlsx")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i, row in df.iterrows():
            title = str(row.get("title", ""))
            url = str(row.get("url", ""))
            duration = str(row.get("duration", ""))
            print(f"\n[{i+1}/{len(df)}] {title}")
            course_data = await scrape_cdu_course(page, url, duration)
            results.append(course_data)

        await browser.close()

    # === OUTPUT SQL FILE ===
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql_lines = []
    for d in results:
        sql = f"""UPDATE courses SET
    course_description = '{d["course_description"]}',
    total_course_duration = '{d["total_course_duration"]}',
    offshore_tuition_fee = '{d["offshore_tuition_fee"]}',
    entry_requirements = '{d["entry_requirements"]}',
    apply_form = '{d["apply_form"]}',
    created_at = '{now}',
    updated_at = '{now}'
WHERE cricos_course_code = '{d["cricos_course_code"]}';"""
        sql_lines.append(sql)

    with open("cdu_update.sql", "w", encoding="utf-8") as f:
        f.write("\n\n".join(sql_lines))

    print("\n✅ Done! SQL file saved as cdu_update.sql")


# === RUN ===
asyncio.run(main())
