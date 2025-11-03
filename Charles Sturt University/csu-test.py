import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    """Rapihin HTML biar satu baris"""
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

def extract_fee_value(html: str) -> str:
    """Ambil nilai dolar pertama dari teks"""
    m = re.search(r"\$([\d,]+)", html)
    return m.group(1).replace(",", "") if m else ""

async def scrape_csu(url):
    data = {
        "url": url,
        "course_description": "",
        "total_course_duration": "3 years",  # contoh manual dulu, nanti baca dari Excel
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "cricos_course_code": "",
        "apply_form": "https://study.csu.edu.au/international/apply"
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print(f"🌐 Opening {url}")
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === DESCRIPTION ===
        desc_div = soup.select_one("div.course-overview")
        if desc_div:
            data["course_description"] = clean_html(str(desc_div))

        # === FEE ===
        fee_div = soup.select_one("div.key-info-content.populate-indicative-fees")
        if fee_div:
            data["offshore_tuition_fee"] = extract_fee_value(fee_div.get_text())

        # === ENTRY REQUIREMENTS ===
        entry_section = soup.select_one("section#entry-requirements")
        if entry_section:
            data["entry_requirements"] = clean_html(str(entry_section))

        # === CRICOS CODE ===
        cricos_span = soup.select_one("div.show-international.cricos-code span.populate-cricos-code")
        if cricos_span:
            data["cricos_course_code"] = cricos_span.get_text(strip=True)

        await browser.close()

    return data


# === TEST RUN ===
url = "https://study.csu.edu.au/international/courses/bachelor-accounting"
result = asyncio.run(scrape_csu(url))

print("\n=== RESULT ===")
for k, v in result.items():
    print(f"{k}: {v[:400]}...\n" if isinstance(v, str) else f"{k}: {v}")
