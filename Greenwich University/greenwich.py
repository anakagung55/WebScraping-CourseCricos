import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from playwright.async_api import async_playwright

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = html.replace("'", "''")
    return html.strip()

# === SANITIZE HTML ===
def sanitize_html(soup: BeautifulSoup) -> str:
    """hapus elemen visual dan ubah heading jadi <p style='font-weight:bold;'>"""
    for tag in soup.find_all(['img', 'svg', 'iframe', 'video', 'picture', 'source']):
        tag.decompose()
    for h in soup.find_all(['h1', 'h2', 'h3']):
        h.name = 'p'
        h['style'] = 'font-weight:bold;'
    return str(soup)

# === EXTRACT DURATION VALUE ===
def extract_duration(text: str) -> str:
    """Cari pola seperti 1–52 weeks, 40-44 weeks, 12 months, 2 years, etc"""
    m = re.search(r"([\d\-–]+ ?(?:week|year|month|semester|term)s?)", text, re.I)
    return m.group(1).strip() if m else ""

# === SCRAPER PER COURSE ===
async def scrape_greenwich_course(page, url, cricos):
    data = {
        "url": url,
        "course_description": "",
        "total_course_duration": "",
        "entry_requirements": "",
        "apply_form": url,  # langsung ke URL course
        "cricos_course_code": cricos
    }

    try:
        print(f"🌐 Scraping {url} ...")
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)  # waktu untuk render konten

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === DESCRIPTION ===
        desc_div = (
            soup.select_one("div.span6.content") or
            soup.select_one("div.elementor-widget-container p") or
            soup.find(lambda t: t.name == "p" and "course" in t.get_text().lower())
        )
        if desc_div:
            desc_html = desc_div.find_parent() or desc_div
            data["course_description"] = clean_html(sanitize_html(BeautifulSoup(str(desc_html), "lxml")))
        else:
            print("⚠️ No description found")

        # === DURATION ===
        dur_tag = soup.find(lambda tag: tag.name in ["div", "p", "li"] and re.search(r"duration", tag.get_text(), re.I))
        if dur_tag:
            data["total_course_duration"] = extract_duration(dur_tag.get_text())
        else:
            print("⚠️ No duration found")

        # === ENTRY REQUIREMENTS ===
        entry_tag = soup.find(lambda tag: tag.name in ["div", "p", "li", "section"] and re.search(r"entry requirement", tag.get_text(), re.I))
        if entry_tag:
            entry_html = entry_tag.find_parent() or entry_tag
            data["entry_requirements"] = clean_html(sanitize_html(BeautifulSoup(str(entry_html), "lxml")))
        else:
            print("⚠️ No entry requirements found")

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")

    return data


# === MAIN LOOP ===
async def main():
    df = pd.read_excel("Greenwich University/greenwich_matched.xlsx")
    results = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i, row in df.iterrows():
            title = str(row.get("title", ""))
            url = str(row.get("url", ""))
            cricos = str(row.get("cricos_code", "")).strip()

            if not cricos:
                print(f"⏭️ Skipped {title} (no CRICOS code)")
                continue

            print(f"\n[{i+1}/{len(df)}] {title}")
            course_data = await scrape_greenwich_course(page, url, cricos)
            results.append(course_data)

        await browser.close()

    # === OUTPUT SQL FILE ===
    def esc(text: str) -> str:
        if not text:
            return ""
        return text.replace("'", "''")

    sql_lines = []
    for d in results:
        sql = f"""UPDATE courses SET
    course_description = '{esc(d["course_description"])}',
    total_course_duration = '{esc(d["total_course_duration"])}',
    entry_requirements = '{esc(d["entry_requirements"])}',
    apply_form = '{esc(d["apply_form"])}',
    created_at = '{now}',
    updated_at = '{now}'
WHERE cricos_course_code = '{esc(d["cricos_course_code"])}';"""
        sql_lines.append(sql)

    with open("greenwich_update.sql", "w", encoding="utf-8") as f:
        f.write("\n\n".join(sql_lines))

    print("\n✅ Done! SQL file saved as greenwich_update.sql")


# === RUN ===
asyncio.run(main())
