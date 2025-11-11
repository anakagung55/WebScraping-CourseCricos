import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

EXCEL_FILE = "Greenwich University/greenwich_matched.xlsx"
OUTPUT_FILE = "greenwich_update.sql"

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = html.replace("'", "''")
    html = re.sub(r"\b(\w+)'(s|ll)\b", r"\1\2", html)
    return html.strip()

# === SANITIZE HTML ===
def sanitize_html(soup: BeautifulSoup) -> str:
    for tag in soup.find_all(['img','svg','iframe','video','source','picture']):
        tag.decompose()
    for h in soup.find_all(['h1','h2','h3','h4']):
        h.name = 'p'
        h['style'] = 'font-weight:bold;'
    return str(soup)

# === EXTRACT DURATION ===
def extract_duration(text: str) -> str:
    m = re.search(r'(\d{1,3}(?:\s*[\-–]\s*\d{1,3})?\s*weeks?)', text, re.I)
    return m.group(1) if m else ""

async def scrape_one(page, url, cricos):
    print(f"\n🌐 Opening {url} ...")
    try:
        await page.goto(url, timeout=120000)
        await page.wait_for_load_state("domcontentloaded")

        # buka entry requirement
        try:
            await page.click("text=Display entry requirements", timeout=5000)
            await page.wait_for_selector("text=English Language Requirement", timeout=8000)
            await page.wait_for_timeout(1500)
        except:
            pass

        soup = BeautifulSoup(await page.content(), "html.parser")

        desc_div = soup.select_one("div.span7.content")
        desc_html = clean_html(sanitize_html(desc_div)) if desc_div else ""

        entry_html = ""
        for div in soup.select("div.entryReq"):
            text = div.get_text(strip=True)
            if len(text) > 50 and ("IELTS" in text or "Requirement" in text):
                entry_html = clean_html(sanitize_html(div))
                break

        duration_text = ""
        for p in soup.find_all("p"):
            if "week" in p.get_text().lower():
                duration_text = extract_duration(p.get_text())
                if duration_text:
                    break

        sql = f"""UPDATE courses SET
    course_description = '{desc_html}',
    total_course_duration = '{duration_text}',
    offshore_tuition_fee = '',
    entry_requirements = '{entry_html}',
    apply_form = '{url}',
    updated_at = NOW()
WHERE cricos_course_code = '{cricos}';"""
        return sql

    except Exception as e:
        print(f"❌ Error at {url}: {e}")
        return f"-- ERROR scraping {url}: {e}"

async def main():
    df = pd.read_excel(EXCEL_FILE)
    sql_outputs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for _, row in df.iterrows():
            url = str(row['url']).strip()
            cricos = str(row['cricos_code']).strip()
            if not url or url == 'nan':
                continue
            sql = await scrape_one(page, url, cricos)
            sql_outputs.append(sql)
            await page.wait_for_timeout(1000)

        await browser.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n\n".join(sql_outputs))
    print(f"\n✅ DONE! All SQL saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
