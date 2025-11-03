import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    return html.strip()

async def scrape_usc(url, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://www.usc.edu.au/international/international-students/apply-now",
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    try:
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")

        # Scroll biar semua content Angular ke-load
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

        # === DURATION ===
        # Ambil dari file excel nanti, tapi kalau ada di halaman bisa fallback
        duration = soup.select_one("div.program-key-details strong.key-figure")
        data["total_course_duration"] = duration.get_text(strip=True) if duration else ""

        # === FEE (ambil langsung dari DOM runtime) ===
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


        # === ENTRY REQUIREMENTS ===
        entry = soup.select_one("div#entry-requirements .card-body")
        data["entry_requirements"] = clean_html(str(entry)) if entry else ""

        # === CRICOS CODE ===
        cricos_div = soup.select_one("strong.key-figure")
        if cricos_div:
            text = cricos_div.get_text(strip=True)
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
        url = "https://www.usc.edu.au/study/courses-and-programs/postgraduate-degrees/doctor-of-philosophy"
        await scrape_usc(url, browser)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
