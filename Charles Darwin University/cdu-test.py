import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    """Bersihkan HTML biar 1 line"""
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

def extract_fee_value(html: str) -> str:
    """Ambil nilai AUD (angka saja)"""
    m = re.search(r"\$([\d,]+)", html)
    return m.group(1).replace(",", "") if m else ""

async def scrape_cdu(url):
    data = {
        "url": url,
        "course_description": "",
        "total_course_duration": "2 years",  # test manual dulu
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "cricos_course_code": "",
        "apply_form": "https://student-cdu.studylink.com/"
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        print(f"🌐 Opening {url}")
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # === Klik tab 'International' ===
        try:
            print("🌏 Clicking International tab...")
            toggle_btn = await page.query_selector("button.js-dialog-toggle")
            if toggle_btn:
                await toggle_btn.scroll_into_view_if_needed()
                await toggle_btn.click()
                print("✅ Clicked International tab.")
                await page.wait_for_timeout(3000)
            else:
                print("⚠️ International toggle not found.")
        except Exception as e:
            print("⚠️ Gagal klik tab International:", e)

        # === Ambil ulang HTML setelah tab diganti ===
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === DESCRIPTION ===
        desc_div = soup.select_one("div#overview.section.rich-text")
        if desc_div:
            data["course_description"] = clean_html(str(desc_div))

        # === FEE ===
        fee_p = soup.find(lambda tag: tag.name == "p" and "$" in tag.get_text())
        if fee_p:
            data["offshore_tuition_fee"] = extract_fee_value(fee_p.get_text())

        # === ENTRY REQUIREMENTS ===
        entry_div = soup.select_one("div#entry-requirements.section.rich-text")
        if entry_div:
            data["entry_requirements"] = clean_html(str(entry_div))

        # === CRICOS ===
        cricos = ""
        for div in soup.select("div.fable__cell.fable__value.align--right"):
            text = div.get_text(strip=True)
            if re.match(r"^\d{6,7}[A-Za-z]?$", text):
                cricos = text
                break
        data["cricos_course_code"] = cricos

        await browser.close()

    return data


# === TEST RUN ===
url = "https://www.cdu.edu.au/study/course/11297nat-course-electrician-minimum-australian-context-gap-11297nat?year=2025"
result = asyncio.run(scrape_cdu(url))

print("\n=== RESULT ===")
for k, v in result.items():
    print(f"{k}: {v[:400]}...\n" if isinstance(v, str) else f"{k}: {v}")
