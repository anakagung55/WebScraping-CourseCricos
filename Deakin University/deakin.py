import re, asyncio, pandas as pd
from bs4 import BeautifulSoup, Comment
from playwright.async_api import async_playwright

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    """Hapus img, svg, komentar, ubah heading ke <p style="font-weight:bold;">"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    # Hapus <img>, <svg>, <script>
    for tag in soup.find_all(["img", "svg", "script"]):
        tag.decompose()

    # Hapus komentar <!-- -->
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Ganti h1–h4 jadi <p style="font-weight:bold;">
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        bold_p = soup.new_tag("p", style="font-weight: bold;")
        bold_p.string = tag.get_text(strip=True)
        tag.replace_with(bold_p)

    cleaned = str(soup)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", cleaned)
    return cleaned.strip()

# === FEE CLEANER ===
def extract_fee_value(text: str) -> str:
    """Ambil angka dolar pertama dan ubah jadi angka bersih"""
    m = re.search(r"\$\s*([\d,]+)", text)
    if not m:
        return ""
    return m.group(1).replace(",", "")

# === ESCAPE SQL ===
def esc_sql(s: str) -> str:
    return s.replace("'", "❛") if s else ""

# === SCRAPE SINGLE COURSE ===
async def scrape_deakin(url, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": url,  # ✅ langsung ambil dari Excel
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    try:
        await page.goto(url, timeout=120000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === COURSE NAME ===
        h1 = soup.find("h1")
        data["course_name"] = h1.get_text(strip=True) if h1 else ""

        # === DESCRIPTION ===
        desc_section = soup.select_one("section#course-overview")
        data["course_description"] = clean_html(str(desc_section)) if desc_section else ""

        # === DURATION ===
        keyfacts_section = soup.find("section", class_="content-box")
        duration = ""
        if keyfacts_section:
            dur_tag = keyfacts_section.find("h3", string=re.compile("Duration", re.I))
            if dur_tag:
                p_tag = dur_tag.find_next("p")
                duration = p_tag.get_text(strip=True) if p_tag else ""
        data["total_course_duration"] = duration

        # === OFFSHORE TUITION FEE ===
        fee_section = soup.select_one("section#fees-and-scholarships")
        fee_val = ""
        if fee_section:
            text = fee_section.get_text(" ", strip=True)
            fee_val = extract_fee_value(text)
        data["offshore_tuition_fee"] = fee_val

        # === ENTRY REQUIREMENTS ===
        entry_html = ""
        entry_start = soup.select_one("section#entry-requirements")
        fee_section = soup.select_one("section#fees-and-scholarships")
        if entry_start and fee_section:
            collected = []
            for sib in entry_start.next_siblings:
                if sib == fee_section:
                    break
                if getattr(sib, "name", None) == "section":
                    collected.append(str(sib))
            entry_html = str(entry_start) + "".join(collected)
        elif entry_start:
            entry_html = str(entry_start)
        data["entry_requirements"] = clean_html(entry_html)

        # === CRICOS CODE ===
        full_text = soup.get_text(" ", strip=True)
        m = re.search(r"\b\d{6,7}[A-Za-z]?\b", full_text)
        data["cricos_course_code"] = m.group(0) if m else ""

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")
    finally:
        await page.close()

    return data

# === MAIN ===
async def main():
    df = pd.read_excel("Deakin University/deakin.xlsx")
    all_data, sqls = [], []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        for i, row in enumerate(df.itertuples(), start=1):
            title = getattr(row, "title", "")
            url = getattr(row, "url", "")

            print(f"\n🔍 ({i}/{len(df)}) Scraping: {title}")
            result = await scrape_deakin(url, browser)
            result["title"] = title

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

            if i % 10 == 0:
                pd.DataFrame(all_data).to_excel("deakin_scraped_progress.xlsx", index=False)
                with open("Deakin University/deakin_scraped_progress.sql", "w", encoding="utf-8") as f:
                    f.write("\n\n".join(sqls))
                print(f"💾 Progress saved ({i}/{len(df)})")

        await browser.close()

    pd.DataFrame(all_data).to_excel("Deakin University/deakin_scraped_all.xlsx", index=False)
    with open("deakin_scraped_all.sql", "w", encoding="utf-8") as f:
        f.write("\n\n".join(sqls))

    print("\n🎯 Done! Saved:\n- deakin_scraped_all.xlsx\n- deakin_scraped_all.sql")


if __name__ == "__main__":
    asyncio.run(main())
