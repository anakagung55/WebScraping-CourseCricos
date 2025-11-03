import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = html.replace("'", "''")  # biar aman di SQL
    return html.strip()

# === EXTRACT FEE VALUE ===
def extract_fee_value(html: str) -> str:
    m = re.search(r"\$([\d,]+)", html)
    return m.group(1).replace(",", "") if m else ""

# === SCRAPER PER COURSE ===
async def scrape_federation_course(page, title, url, duration):
    print(f"🌐 Scraping: {title}")
    data = {
        "course_name": title,
        "url": url,
        "total_course_duration": duration,
        "course_description": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "cricos_course_code": "",
        "apply_form": "https://apply.federation.edu.au/"
    }

    try:
        await page.goto(url, timeout=90000)
        await page.wait_for_selector("button:has-text('International')", timeout=30000)
        await page.click("button:has-text('International')")
        await page.wait_for_timeout(4000)

        # scroll agar semua lazy content muncul
        await page.mouse.wheel(0, 6000)
        await page.wait_for_timeout(2000)

        # klik accordion "How to apply"
        try:
            await page.click("button:has-text('How to apply')")
            await page.wait_for_timeout(2000)
        except:
            pass

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === DESCRIPTION ===
        desc_div = soup.select_one("div.wysiwyg.prose.line-clamp-14.overflow-hidden")
        if desc_div:
            data["course_description"] = clean_html(str(desc_div))

        # === FEE ===
        fee_div = soup.find(lambda tag: tag.name == "div" and "$" in tag.get_text())
        if fee_div:
            data["offshore_tuition_fee"] = extract_fee_value(fee_div.get_text())

        # === ENTRY REQUIREMENTS ===
        entry_h2 = soup.find("h2", string=re.compile("Entry requirements", re.I))
        if entry_h2:
            parent_section = entry_h2.find_parent("section")
            if parent_section:
                data["entry_requirements"] = clean_html(str(parent_section))

        # === CRICOS CODE (pakai evaluate langsung biar pasti muncul) ===
        cricos_code = await page.evaluate("""
            () => {
                const dts = Array.from(document.querySelectorAll('dt'));
                for (const dt of dts) {
                    if (dt.textContent.toLowerCase().includes('cricos')) {
                        const dd = dt.nextElementSibling;
                        return dd ? dd.textContent.trim() : '';
                    }
                }
                return '';
            }
        """)
        data["cricos_course_code"] = cricos_code

        print(f"✅ {title} → CRICOS: {cricos_code}")

    except Exception as e:
        print(f"⚠️ Error scraping {title}: {e}")

    return data

# === MAIN ===
async def main():
    df = pd.read_excel("Federation University/federation.xlsx")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i, row in df.iterrows():
            title = str(row["title"])
            url = str(row["url"])
            duration = str(row.get("duration", ""))
            result = await scrape_federation_course(page, title, url, duration)
            results.append(result)

        await browser.close()

    # === SIMPAN KE SQL FILE ===
    sql_lines = []
    for d in results:
        sql = f"""UPDATE courses SET
    course_description = '{d["course_description"]}',
    total_course_duration = '{d["total_course_duration"]}',
    offshore_tuition_fee = '{d["offshore_tuition_fee"]}',
    entry_requirements = '{d["entry_requirements"]}',
    apply_form = '{d["apply_form"]}'
WHERE cricos_course_code = '{d["cricos_course_code"]}';"""
        sql_lines.append(sql)

    with open("federation_update.sql", "w", encoding="utf-8") as f:
        f.write("\n\n".join(sql_lines))

    print("\n✅ Done! Saved to federation_update.sql")

# === RUN ===
asyncio.run(main())
