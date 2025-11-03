import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    return html.strip()

async def scrape_torrens(url, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://apply.torrens.edu.au/",
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    try:
        await page.goto(url, timeout=120000, wait_until="networkidle")

        # scroll biar semua lazy component ke-load
        for _ in range(5):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(1)
        # tunggu CRICOS kalau ada
        try:
            await page.wait_for_selector("div.hero-banner__card__item", timeout=8000)
        except:
            pass

        await asyncio.sleep(2)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === COURSE NAME ===
        h1 = soup.find("h1")
        if h1:
            data["course_name"] = h1.get_text(strip=True)

        # === DESCRIPTION ===
        desc = soup.select_one("div.course-overview__left")
        data["course_description"] = clean_html(str(desc)) if desc else ""

        # === DURATION ===
        durations = soup.select("div.course-card-panel__value")
        for d in durations:
            txt = d.get_text(strip=True)
            if re.search(r"\d+\s*year", txt, re.I):
                data["total_course_duration"] = txt
                break

        # === ENTRY REQUIREMENTS ===
        entry = soup.select_one("div.component.admission-criteria")
        if entry:
            data["entry_requirements"] = clean_html(str(entry))

        # === CRICOS CODE ===
        # Coba cari di elemen yang mengandung CRICOS
        cricos_divs = soup.select("div.hero-banner__card__item")
        for c in cricos_divs:
            text = c.get_text(strip=True)
            if "CRICOS" in text:
                m = re.search(r"\b\d{6,7}[A-Z]?\b", text)
                if m:
                    data["cricos_course_code"] = m.group(0)
                    break

        # Fallback: regex ke seluruh HTML kalau belum ketemu
        if not data["cricos_course_code"]:
            m = re.search(r"CRICOS\s*(?:code\s*)?(\d{6,7}[A-Z]?)", html, re.I)
            if m:
                data["cricos_course_code"] = m.group(1)

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
        url = "https://www.torrens.edu.au/courses/education/master-of-education-leadership-and-innovation"
        await scrape_torrens(url, browser)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
