import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    return html.strip()

async def scrape_scu(url, duration_from_excel, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": duration_from_excel or "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://www.scu.edu.au/apply/international-applications/",
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    try:
        await page.goto(url, timeout=120000, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # === PILIH INTERNATIONAL MODE ===
        try:
            await page.select_option("#course-location", "international")
            await asyncio.sleep(3)
            print("🌍 Switched to International mode")
        except Exception:
            print("⚠️ International selector not found or already active")

        # scroll biar semua bagian muncul
        for _ in range(12):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(0.6)
        await asyncio.sleep(1.5)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === COURSE NAME ===
        h1 = soup.find("h1")
        data["course_name"] = h1.get_text(strip=True) if h1 else ""

        # === DESCRIPTION ===
        desc = soup.select_one("div.overview__text")
        data["course_description"] = clean_html(str(desc)) if desc else ""

        # === DURATION ===
        durations = soup.select("div.course-snapshot__text")
        for d in durations:
            text = d.get_text(strip=True)
            if re.search(r"\d+\s*(year|yr)", text, re.I):
                data["total_course_duration"] = text
                break

        # === FEE ===
        fee_cell = soup.find("td", string=re.compile(r"\$"))
        if fee_cell:
            m = re.search(r"\$([\d,]+)", fee_cell.get_text())
            if m:
                data["offshore_tuition_fee"] = m.group(1).replace(",", "")

        # === ENTRY REQUIREMENTS ===
        entry = soup.select_one("div.course-content__inner")
        data["entry_requirements"] = clean_html(str(entry)) if entry else ""

        # === CRICOS CODE ===
        cricos_cell = soup.find("td", string=re.compile(r"\d{6,7}[A-Z]?"))
        if cricos_cell:
            text = cricos_cell.get_text(strip=True)
            if re.match(r"^\d{6,7}[A-Z]?$", text):
                data["cricos_course_code"] = text

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")
    finally:
        await page.close()

    return data


async def main():
    df = pd.read_excel("scu.xlsx")
    all_data, sqls = [], []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        for i, row in enumerate(df.itertuples(), start=1):
            url = getattr(row, "link", "") if hasattr(row, "link") else getattr(row, "url", "")
            duration = getattr(row, "duration", "")

            if not isinstance(url, str) or not url.startswith("http"):
                print(f"⚠️ Skipped invalid URL: {url}")
                continue

            print(f"\n🔍 ({i}/{len(df)}) Scraping: {url}")
            result = await scrape_scu(url, duration, browser)

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

            # Simpan tiap 10 course
            if i % 10 == 0:
                pd.DataFrame(all_data).to_excel("scu_scraped_progress.xlsx", index=False)
                with open("scu_scraped_progress.sql", "w", encoding="utf-8") as f:
                    f.write("\n".join(sqls))
                print(f"💾 Progress saved ({i}/{len(df)}) ...")

        await browser.close()

    # Final save
    pd.DataFrame(all_data).to_excel("scu_scraped_all.xlsx", index=False)
    with open("scu_scraped_all.sql", "w", encoding="utf-8") as f:
        f.write("\n".join(sqls))

    print("\n🎯 Done! Saved final outputs:")
    print("- scu_scraped_all.xlsx")
    print("- scu_scraped_all.sql")


if __name__ == "__main__":
    asyncio.run(main())
