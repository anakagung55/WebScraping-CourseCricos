import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    return html.strip()


# === SCRAPER FUNCTION ===
async def scrape_notredame(url, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://www.notredame.edu.au/forms/admissions/apply-direct",
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    try:
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")

        # scroll biar elemen JS kebuka semua
        for _ in range(15):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(0.6)
        await asyncio.sleep(2)

        # pastikan muncul
        try:
            await page.wait_for_selector("span.details-listing__content", timeout=15000)
        except:
            print("⚠️ details-listing__content not detected, continuing...")

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === BASIC INFO ===
        h1 = soup.find("h1")
        data["course_name"] = h1.get_text(strip=True) if h1 else ""

        desc = soup.select_one("div.accordion__content[id^='Why_study_this_degree']")
        data["course_description"] = clean_html(str(desc)) if desc else ""

        entry = soup.select_one("div.accordion__content[id^='Entry_requirements']")
        data["entry_requirements"] = clean_html(str(entry)) if entry else ""

        # === DURATION & CRICOS berdasarkan li > span.details-listing__title
        pairs = await page.evaluate("""
            Array.from(document.querySelectorAll('li')).map(li => {
                const title = li.querySelector('.details-listing__title')?.textContent?.trim() || '';
                const value = li.querySelector('.details-listing__content')?.textContent?.trim() || '';
                return { title, value };
            });
        """)

        for p in pairs:
            title = (p.get("title") or "").lower()
            value = (p.get("value") or "").strip()
            if not value:
                continue

            # DURATION
            if "duration" in title and not data["total_course_duration"]:
                data["total_course_duration"] = value

            # CRICOS
            if "cricos" in title and not data["cricos_course_code"]:
                data["cricos_course_code"] = value

        # === Fallback jika belum ketemu ===
        if not data["total_course_duration"] or not data["cricos_course_code"]:
            runtime_spans = await page.evaluate("""
                Array.from(document.querySelectorAll('span.details-listing__content'))
                     .map(e => e.textContent.trim());
            """)

            if not data["total_course_duration"]:
                for t in runtime_spans:
                    if 'year' in t.lower() or 'full' in t.lower():
                        data["total_course_duration"] = t
                        break

            if not data["cricos_course_code"]:
                for t in runtime_spans:
                    s = t.strip().replace(" ", "")
                    if 7 <= len(s) <= 8 and s[:-1].isdigit():
                        data["cricos_course_code"] = s
                        break

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


# === MAIN TEST ===
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        url = "https://www.notredame.edu.au/programs/school-of-business/undergraduate/bachelor-of-accounting"
        await scrape_notredame(url, browser)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
