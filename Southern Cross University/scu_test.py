import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    return html.strip()


async def scrape_scu(url, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
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

        # scroll agar konten kebuka semua
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

    print("\n✅ Scraped Result Preview:")
    for k, v in data.items():
        if isinstance(v, str):
            print(f"- {k}: {v[:200]}{'...' if len(v) > 200 else ''}")
        else:
            print(f"- {k}: {v}")
    return data


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        url = "https://www.scu.edu.au/study/courses/associate-degree-of-international-hotel-and-tourism-management-2206700/2026/"
        await scrape_scu(url, browser)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
