import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from urllib.parse import urlparse

def clean_html(html: str) -> str:
    """Clean HTML, hilangkan img, ubah h2/h3 jadi <p style=bold>"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    # Hapus gambar
    for img in soup.find_all("img"):
        img.decompose()

    # Ganti heading jadi <p style="font-weight:bold;">
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        bold_p = soup.new_tag("p", style="font-weight: bold;")
        bold_p.string = tag.get_text(strip=True)
        tag.replace_with(bold_p)

    cleaned = str(soup)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", cleaned)
    return cleaned.strip()

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def normalize_fee(text):
    """Ambil angka dari string fee"""
    if not text:
        return ""
    m = re.search(r"\$?([\d,]+)", text)
    if m:
        return re.sub(r"[^\d]", "", m.group(1))
    return ""

def esc_sql(s: str) -> str:
    """Escape SQL (ganti ' jadi ❛)"""
    return s.replace("'", "❛") if s else ""

async def scrape_qut(url, browser):
    """Scrape single QUT course page"""
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "cricos_course_code": ""
    }

    # Skip link internal/pdf
    if any(x in url for x in ["pdf.courses.qut.edu.au", "qutvirtual4.qut.edu.au"]):
        print(f"⏭️ Skipped internal/PDF link: {url}")
        return data

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    if "international" not in url:
        url = url.rstrip("?") + "?international"

    try:
        await page.goto(url, timeout=120000, wait_until="domcontentloaded")
        for _ in range(5):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(1)
        await asyncio.sleep(2)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === COURSE NAME ===
        h1 = soup.find("h1")
        data["course_name"] = h1.get_text(strip=True) if h1 else ""

        # === DESCRIPTION ===
        desc = soup.select_one("div[data-course-map-key='detailsItems']")
        data["course_description"] = clean_html(str(desc)) if desc else ""

        # === DURATION ===
        dur = soup.select_one("li[data-course-map-key='quickBoxDurationINTFt']")
        data["total_course_duration"] = dur.get_text(strip=True) if dur else ""

        # === FEE (ambil nilai USD/AUD aktual) ===
        data["offshore_tuition_fee"] = ""
        fee_block = soup.select_one("div[data-course-map-key='feeTabCurrentINT']")

        if fee_block:
            # Cari semua angka dengan simbol $ di blok fee
            fees = re.findall(r"\$[\d,]+", fee_block.get_text())
            if fees:
                # Ambil fee terbesar (menghindari 2026 dsb)
                fee_nums = [int(x.replace("$", "").replace(",", "")) for x in fees if x]
                if fee_nums:
                    data["offshore_tuition_fee"] = str(max(fee_nums))


        # === ENTRY REQUIREMENTS ===
        req_int = soup.select_one("div.requirements-international.col-lg-12")
        if req_int:
            for bad in req_int.select(".country-select-wrap, .qualification-type-select-wrap"):
                bad.decompose()
            data["entry_requirements"] = clean_html(str(req_int))
        else:
            entry = soup.select_one("div[data-course-map-key='reqTabCqp']")
            data["entry_requirements"] = clean_html(str(entry)) if entry else ""

        # === CRICOS CODE ===
        cricos = ""
        ul_cricos = soup.select_one("ul[data-course-map-key='quickBoxCricos'] li")
        if ul_cricos:
            cricos = ul_cricos.get_text(strip=True)
        else:
            span_cricos = soup.select_one("span[title*='International students can apply']")
            if span_cricos:
                cricos = span_cricos.get_text(strip=True)
            else:
                m = re.search(r"\b\d{7}[A-Z]?\b", html)
                cricos = m.group(0) if m else ""
        data["cricos_course_code"] = cricos.strip()

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")

    finally:
        await page.close()

    return data


async def main():
    df = pd.read_excel("Queensland University/qut.xlsx")

    if "url" not in df.columns:
        raise ValueError("❌ Kolom 'url' tidak ditemukan di Excel!")

    urls = df["url"].dropna().unique().tolist()
    all_data = []
    sqls = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        for i, row in enumerate(df.itertuples(), start=1):
            title = getattr(row, "title", "")
            url = getattr(row, "url", "")

            if not is_valid_url(url):
                print(f"⚠️ Skipped invalid URL: {url}")
                continue

            print(f"\n🔍 ({i}/{len(df)}) Scraping: {title}")
            result = await scrape_qut(url, browser)
            result["title"] = title
            result["apply_form"] = url   # ✅ apply_form ambil langsung dari kolom Excel (link course)

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

            # === SAVE PROGRESS TIAP 10 ===
            if i % 10 == 0:
                pd.DataFrame(all_data).to_excel("qut_scraped_progress.xlsx", index=False)
                with open("qut_scraped_progress.sql", "w", encoding="utf-8") as f:
                    f.write("\n".join(sqls))
                print(f"💾 Progress saved ({i}/{len(df)}) ...")

        await browser.close()

    # === FINAL SAVE ===
    pd.DataFrame(all_data).to_excel("qut_scraped_all.xlsx", index=False)
    with open("qut_scraped_all.sql", "w", encoding="utf-8") as f:
        f.write("\n".join(sqls))
    print("\n🎯 Done! Saved final outputs:\n- qut_scraped_all.xlsx\n- qut_scraped_all.sql")


if __name__ == "__main__":
    asyncio.run(main())
