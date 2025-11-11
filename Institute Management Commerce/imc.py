import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


# === CLEAN HTML ===
def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()


# === EXTRACT DURATION DARI HALAMAN ===
def extract_duration(text: str) -> str:
    """Cari pola durasi seperti '52 weeks', '1 year', '2 years', dst"""
    match = re.search(r'(\d{1,3}\s*(weeks?|months?|years?))', text, re.IGNORECASE)
    return match.group(1) if match else ""


# === SCRAPER PER COURSE ===
async def scrape_imc_course(page, url, cricos, duration, fee):
    data = {
        "course_description": "",
        "total_course_duration": duration,
        "offshore_tuition_fee": fee,
        "entry_requirements": "",
        "apply_form": url,
        "cricos_course_code": cricos
    }

    try:
        print(f"🌐 Scraping {url} ...")
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === DESCRIPTION ===
        desc_div = soup.select_one("div.elementor-widget-container p")
        if desc_div:
            parent_div = desc_div.find_parent("div", class_="elementor-widget-container")
            data["course_description"] = clean_html(str(parent_div or desc_div))
        else:
            print("⚠️ No description found")

        # === ENTRY REQUIREMENTS (gabung Entry + English Language) ===
        entry_blocks = []
        for box in soup.select("div.elementor-widget-icon-box"):
            title_el = box.select_one("h5.elementor-icon-box-title")
            if not title_el:
                continue
            title_text = title_el.get_text(strip=True).lower()
            if "entry requirement" in title_text or "english language requirement" in title_text:
                entry_blocks.append(clean_html(str(box)))

        if entry_blocks:
            data["entry_requirements"] = " ".join(entry_blocks)
        else:
            print("⚠️ No entry requirements found")

        # === CARI DURATION DI HALAMAN JIKA KOSONG ===
        if not data["total_course_duration"] or data["total_course_duration"].lower() in ["nan", "none", ""]:
            duration_found = ""
            for p in soup.find_all(["p", "li", "span"]):
                if "week" in p.get_text().lower() or "year" in p.get_text().lower():
                    duration_found = extract_duration(p.get_text())
                    if duration_found:
                        data["total_course_duration"] = duration_found
                        print(f"📆 Duration found from page: {duration_found}")
                        break

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")

    return data


# === MAIN LOOP ===
async def main():
    df = pd.read_excel("Institute Management Commerce/imc_merged.xlsx")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i, row in df.iterrows():
            title = str(row.get("title", ""))
            url = str(row.get("url", ""))
            cricos = str(row.get("cricos_code", "")).strip()
            duration = str(row.get("duration", "")).strip()
            fee = str(row.get("offshore_fee", "")).strip()

            if not url or not cricos:
                print(f"⏭️ Skipped {title} (missing URL or CRICOS)")
                continue

            print(f"\n[{i+1}/{len(df)}] {title}")
            course_data = await scrape_imc_course(page, url, cricos, duration, fee)
            results.append(course_data)

        await browser.close()

    # === ESCAPE QUOTES UNTUK SQL ===
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
    apply_form = '{escape_sql(d["apply_form"])}',
    updated_at = NOW()
WHERE cricos_course_code = '{escape_sql(d["cricos_course_code"])}';"""
        sql_lines.append(sql)

    with open("imc_update.sql", "w", encoding="utf-8") as f:
        f.write("\n\n".join(sql_lines))

    print("\n✅ Done! SQL file saved as imc_update.sql")


# === RUN ===
asyncio.run(main())
