import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    return html.strip()

async def scrape_usc(url, duration_from_excel, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": duration_from_excel or "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://www.usc.edu.au/international/international-students/apply-now",
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    try:
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")

        # Scroll agar AngularJS render sempurna
        for _ in range(15):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(0.6)
        await asyncio.sleep(2)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === COURSE NAME ===
        h1 = soup.find("h1")
        data["course_name"] = h1.get_text(strip=True) if h1 else ""

        # === DESCRIPTION ===
        desc = soup.select_one("div.card-body[ng-transclude]")
        data["course_description"] = clean_html(str(desc)) if desc else ""

        # === ENTRY REQUIREMENTS ===
        entry = soup.select_one("div#entry-requirements .card-body")
        data["entry_requirements"] = clean_html(str(entry)) if entry else ""

        # === CRICOS CODE ===
        cricos_div = soup.select_one("strong.key-figure")
        if cricos_div:
            text = cricos_div.get_text(strip=True)
            if re.match(r"^\d{6,7}[A-Z]?$", text):
                data["cricos_course_code"] = text

        # === FEE (runtime DOM) ===
        try:
            fee_texts = await page.evaluate("""
                Array.from(document.querySelectorAll("div[audience='international'] strong.key-figure"))
                     .map(e => e.textContent.trim());
            """)
            for f in fee_texts:
                if "$" in f:
                    m = re.search(r"\$([\d,]+)", f)
                    if m:
                        data["offshore_tuition_fee"] = m.group(1).replace(",", "")
                        break
        except Exception as e:
            print(f"⚠️ Fee extract failed: {e}")

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")

    finally:
        await page.close()

    return data


async def main():
    df = pd.read_excel("usc.xlsx")
    all_data, sqls = [], []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        for i, row in enumerate(df.itertuples(), start=1):
            url = getattr(row, "link", "")
            duration = getattr(row, "duration", "")

            if not isinstance(url, str) or not url.startswith("http"):
                print(f"⚠️ Skipped invalid URL: {url}")
                continue

            print(f"\n🔍 ({i}/{len(df)}) Scraping: {url}")
            result = await scrape_usc(url, duration, browser)

            if not result["course_name"]:
                print(f"⚠️ Skipped or failed: {url}")
                continue

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

            # Simpan progress tiap 10
            if i % 10 == 0:
                pd.DataFrame(all_data).to_excel("usc_scraped_progress.xlsx", index=False)
                with open("usc_scraped_progress.sql", "w", encoding="utf-8") as f:
                    f.write("\n".join(sqls))
                print(f"💾 Progress saved ({i}/{len(df)}) ...")

        await browser.close()

    # Final save
    pd.DataFrame(all_data).to_excel("usc_scraped_all.xlsx", index=False)
    with open("usc_scraped_all.sql", "w", encoding="utf-8") as f:
        f.write("\n".join(sqls))

    print("\n🎯 Done! Saved final outputs:")
    print("- usc_scraped_all.xlsx")
    print("- usc_scraped_all.sql")


if __name__ == "__main__":
    asyncio.run(main())
