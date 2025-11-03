import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

# === SCRAPE ENTRY REQUIREMENT (DIPAKAI UNTUK SEMUA COURSE) ===
async def scrape_entry_requirements(browser):
    entry_url = "https://aih.edu.au/students/entry-requirements/international-students/"
    page = await browser.new_page()
    await page.goto(entry_url, timeout=90000)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    section = soup.select_one("section.vc_section.gray_boxrow.pb-65")
    entry_html = clean_html(str(section)) if section else ""
    await page.close()
    return entry_html

# === SCRAPE SATU COURSE (TEST) ===
async def scrape_course(browser):
    url = "https://aih.edu.au/courses/bachelor-of-accounting/"
    data = {
        "url": url,
        "course_description": "",
        "cricos_course_code": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://aih.edu.au",
    }

    page = await browser.new_page()
    await page.goto(url, timeout=90000)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    # DESC
    desc = soup.select_one(".wpb_text_column.wpb_content_element.montserrat.subpagetext_p.container_1000 .wpb_wrapper")
    if desc:
        data["course_description"] = clean_html(str(desc))

    # CRICOS
    cricos_match = re.search(r"CRICOS Code:\s*([A-Z0-9]+)", html)
    if cricos_match:
        data["cricos_course_code"] = cricos_match.group(1)

    # DURATION
    dur_divs = soup.find_all("div", class_="wpb_wrapper")
    for div in dur_divs:
        if "full time" in div.get_text(strip=True).lower():
            data["total_course_duration"] = div.get_text(strip=True)
            break

    # FEE (ambil angka terbesar)
    fee_tags = soup.select("h2.keygreen_h2")
    if fee_tags:
        fees = []
        for tag in fee_tags:
            txt = tag.get_text(strip=True)
            num = re.sub(r"[^\d]", "", txt)
            if num.isdigit():
                fees.append(int(num))
        if fees:
            data["offshore_tuition_fee"] = str(max(fees))

    await page.close()
    return data

# === MAIN ===
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        print("Scraping global entry requirements...")
        ENTRY_HTML = await scrape_entry_requirements(browser)

        print("Scraping single course...")
        course = await scrape_course(browser)
        course["entry_requirements"] = ENTRY_HTML  # pakai global entry req
        await browser.close()

    # OUTPUT SQL
    if course["cricos_course_code"]:
        sql = f"""
UPDATE courses SET
    course_description = '{course["course_description"]}',
    total_course_duration = '{course["total_course_duration"]}',
    offshore_tuition_fee = '{course["offshore_tuition_fee"]}',
    entry_requirements = '{course["entry_requirements"]}',
    created_at = NOW(),
    updated_at = NOW(),
    apply_form = '{course["apply_form"]}'
WHERE cricos_course_code = '{course["cricos_course_code"]}';
"""
        print(sql)
    else:
        print("❌ CRICOS Code not found")

asyncio.run(main())
