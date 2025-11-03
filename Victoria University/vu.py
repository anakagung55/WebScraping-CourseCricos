import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    return html.strip()

# === EXTRACT FEE ===
def extract_fee(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"AU\$?([\d,]+)", text)
    if not m:
        return ""
    val = int(m.group(1).replace(",", "")) * 2
    return str(val)

# === SCRAPE SINGLE COURSE ===
async def scrape_vu(url, duration, browser, retry_domestic=True):
    """Scrape satu halaman course VU dengan fallback ke versi non-/international jika kosong"""
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": duration,
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://eaams.vu.edu.au/portal/Apply.aspx",
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    try:
        await page.goto(url, timeout=120000, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Cek apakah konten kosong (biasanya /international)
        empty_page = not soup.select_one("div#overview") and not soup.select_one("div#entry-requirements")

        if empty_page and retry_domestic and "/international" in url:
            # coba fallback ke versi tanpa /international
            new_url = url.replace("/international", "")
            print(f"🔁 Empty international page detected, retrying with domestic: {new_url}")
            await page.close()
            return await scrape_vu(new_url, duration, browser, retry_domestic=False)

        # === COURSE NAME ===
        h1 = soup.find("h1")
        data["course_name"] = h1.get_text(strip=True) if h1 else ""

        # === DESCRIPTION ===
        desc = soup.select_one("div#overview")
        data["course_description"] = clean_html(str(desc)) if desc else ""

        # === FEE ===
        fee_tag = soup.find("div", class_="vu-markup__inner", string=re.compile("AU"))
        if not fee_tag:
            fee_tag = soup.find("p", string=re.compile("AU"))
        if fee_tag:
            data["offshore_tuition_fee"] = extract_fee(fee_tag.get_text())

        # === ENTRY REQUIREMENTS ===
        entry = soup.select_one("div#entry-requirements")
        data["entry_requirements"] = clean_html(str(entry)) if entry else ""

        # === CRICOS CODE ===
        cricos = ""
        spans = soup.select("span.vu-course-each-basics-value")
        for s in spans:
            text = s.get_text(strip=True)
            if re.match(r"^\d{6,7}[A-Za-z]?$", text):
                cricos = text
                break
        if not cricos:
            m = re.search(r"\b\d{6,7}[A-Z]?\b", soup.get_text())
            if m:
                cricos = m.group(0)
        data["cricos_course_code"] = cricos

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")
    finally:
        await page.close()

    return data

# === MAIN ===
async def main():
    df = pd.read_excel("vu.xlsx")
    all_data = []
    sqls = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        for i, row in enumerate(df.itertuples(), start=1):
            title = getattr(row, "title", "")
            url = getattr(row, "url", "")
            duration = getattr(row, "duration", "")

            print(f"\n🔍 ({i}/{len(df)}) Scraping: {title}")
            result = await scrape_vu(url, duration, browser)
            result["title"] = title
            all_data.append(result)

            cricos = result["cricos_course_code"] or "UNKNOWN"
            def esc(s): return s.replace("'", "''") if s else ""

            sql = f"""
UPDATE courses SET
    course_description = '{esc(result["course_description"])}',
    total_course_duration = '{esc(result["total_course_duration"])}',
    offshore_tuition_fee = '{esc(result["offshore_tuition_fee"])}',
    entry_requirements = '{esc(result["entry_requirements"])}',
    apply_form = '{esc(result["apply_form"])}'
WHERE cricos_course_code = '{cricos}';
"""
            sqls.append(sql)

            if i % 10 == 0:
                pd.DataFrame(all_data).to_excel("vu_scraped_progress.xlsx", index=False)
                with open("vu_scraped_progress.sql", "w", encoding="utf-8") as f:
                    f.write("\n".join(sqls))
                print(f"💾 Progress saved ({i}/{len(df)})")

        await browser.close()

    pd.DataFrame(all_data).to_excel("vu_scraped_all.xlsx", index=False)
    with open("vu_scraped_all.sql", "w", encoding="utf-8") as f:
        f.write("\n".join(sqls))

    print("\n✅ Done! Saved:\n- vu_scraped_all.xlsx\n- vu_scraped_all.sql")

if __name__ == "__main__":
    asyncio.run(main())
