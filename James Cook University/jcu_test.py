import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    return html.strip()

async def scrape_jcu(url, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "",
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    try:
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === COURSE NAME ===
        h1 = soup.find("h1")
        data["course_name"] = h1.get_text(strip=True) if h1 else ""

        # === DESCRIPTION ===
        desc = soup.select_one("p.course-banner__text")
        data["course_description"] = clean_html(str(desc)) if desc else ""

        # === DURATION ===
        dur_tile = soup.select_one("div.course-fast-facts__tile.fast-facts-duration div.course-fast-facts__tile__body-top p")
        if dur_tile:
            data["total_course_duration"] = dur_tile.get_text(strip=True)

        # === FEE ===
        fee_tile = soup.select_one("div.course-fast-facts__tile.fast-facts-fees div.course-fast-facts__tile__body-top__lrg p")
        if fee_tile:
            m = re.search(r"\$([\d,]+)", fee_tile.get_text())
            if m:
                data["offshore_tuition_fee"] = m.group(1).replace(",", "")

        # === ENTRY REQUIREMENTS ===
        entry_tile = soup.select_one("div.course-fast-facts__tile.fast-facts-entry-requirements div.course-fast-facts__tile__body-top")
        data["entry_requirements"] = clean_html(str(entry_tile)) if entry_tile else ""

        # === CRICOS CODE ===
        cricos_tile = soup.select_one("div.course-fast-facts__tile.fast-facts-codes div.cricos-code p")
        if cricos_tile:
            data["cricos_course_code"] = cricos_tile.get_text(strip=True)

        # === APPLY FORM ===
        # (Anda belum menentukan link spesifik — saya sisakan kosong atau Anda bisa isi jika tahu)
        data["apply_form"] = ""  # <-- mohon isi jika sudah tahu spesifik link apply JCU

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")
    finally:
        await page.close()

    print("\n✅ Scraped Result Preview:")
    for k, v in data.items():
        print(f"- {k}: {v}")
    return data

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        url = "https://www.jcu.edu.au/courses/diploma-of-business-pathway"
        await scrape_jcu(url, browser)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
