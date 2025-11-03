import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from urllib.parse import urlparse

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    return html.strip()

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

async def scrape_qut(url, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://www.qut.edu.au/",
        "cricos_course_code": ""
    }

    # skip link PDF & QUT Virtual
    if any(x in url for x in ["pdf.courses.qut.edu.au", "qutvirtual4.qut.edu.au"]):
        print(f"⏭️ Skipped internal or PDF link: {url}")
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
        data["course_description"] = str(desc) if desc else ""

        # === DURATION ===
        dur = soup.select_one("li[data-course-map-key='quickBoxDurationINTFt']")
        data["total_course_duration"] = dur.get_text(strip=True) if dur else ""

        # === FEE ===
        fee = soup.select_one("div[data-course-map-key='feeTabCurrentINT'] p")
        if fee:
            m = re.search(r"\$[\d,]+", fee.get_text())
            data["offshore_tuition_fee"] = m.group(0) if m else ""

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
        data["cricos_course_code"] = cricos

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")

    finally:
        await page.close()

    return data


async def main():
    df = pd.read_excel("Queensland University/qut.xlsx")
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
            if any(x in url for x in ["pdf.courses.qut.edu.au", "qutvirtual4.qut.edu.au"]):
                print(f"⏭️ Skipped internal or PDF link: {url}")
                continue

            print(f"\n🔍 ({i}/{len(df)}) Scraping: {title}")
            result = await scrape_qut(url, browser)
            result["title"] = title

            if result["course_name"]:
                all_data.append(result)
                cricos = result["cricos_course_code"] or "UNKNOWN"
                def esc(s): return s.replace("'", "''") if s else ""

                sql = f"""
UPDATE courses SET
    course_description = '{esc(result["course_description"])}',
    total_course_duration = '{esc(result["total_course_duration"])}',
    offshore_tuition_fee = '{esc(result["offshore_tuition_fee"])}',
    entry_requirements = '{esc(result["entry_requirements"])}',
    apply_form = '{(result["apply_form"])}'
WHERE cricos_course_code = '{cricos}';
"""
                sqls.append(sql)
            else:
                print(f"⚠️ Skipped or failed: {title}")

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
