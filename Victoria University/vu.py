import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    """Remove images, SVG icons, and convert headings to bold paragraphs."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    # Remove all <img> and <svg> icons
    for tag in soup.find_all(["img", "svg"]):
        tag.decompose()

    # Replace heading tags with <p style="font-weight:bold;">
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        bold_p = soup.new_tag("p", style="font-weight: bold;")
        bold_p.string = tag.get_text(strip=True)
        tag.replace_with(bold_p)

    # Clean up whitespace and repeated <br>
    cleaned = str(soup)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", cleaned)
    return cleaned.strip()

# === EXTRACT FEE ===
def extract_fee(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"AU\$?([\d,]+)", text)
    if not m:
        return ""
    val = int(m.group(1).replace(",", "")) * 2
    return str(val)

# === ESCAPE SQL ===
def esc_sql(s: str) -> str:
    return s.replace("'", "❛") if s else ""

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
        data["cricos_course_code"] = cricos.strip()

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")
    finally:
        await page.close()

    return data


# === MAIN ===
async def main():
    df = pd.read_excel("Victoria University/vu.xlsx")
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
            result["apply_form"] = url  # ✅ langsung ambil dari kolom Excel

            cricos = result["cricos_course_code"].strip()
            if not cricos:
                print(f"⚠️ Skipped (no CRICOS): {title}")
                continue

            all_data.append(result)

            sql = f"""
UPDATE courses SET
    course_description = '{esc_sql(result["course_description"])}',
    total_course_duration = '{esc_sql(result["total_course_duration"])}',
    offshore_tuition_fee = '{esc_sql(result["offshore_tuition_fee"])}',
    entry_requirements = '{esc_sql(result["entry_requirements"])}',
    apply_form = '{esc_sql(result["apply_form"])}',
    created_at = NOW(),
    updated_at = NOW()
WHERE cricos_course_code = '{esc_sql(cricos)}';
"""
            sqls.append(sql)
            print(f"✅ Success: {cricos}")

            # === AUTO-SAVE TIAP 10 COURSE ===
            if i % 10 == 0:
                pd.DataFrame(all_data).to_excel("vu_scraped_progress.xlsx", index=False)
                with open("vu_scraped_progress.sql", "w", encoding="utf-8") as f:
                    f.write("\n".join(sqls))
                print(f"💾 Progress saved ({i}/{len(df)})")

        await browser.close()

    # === FINAL SAVE ===
    pd.DataFrame(all_data).to_excel("vu_scraped_all.xlsx", index=False)
    with open("vu_scraped_all.sql", "w", encoding="utf-8") as f:
        f.write("\n".join(sqls))

    print("\n🎯 Done! Saved all results:\n- vu_scraped_all.xlsx\n- vu_scraped_all.sql")


if __name__ == "__main__":
    asyncio.run(main())
