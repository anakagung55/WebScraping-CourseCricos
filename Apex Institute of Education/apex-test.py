import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    return re.sub(r"\s+", " ", html.strip()) if html else ""

async def scrape_apex():
    url = "https://vet.apexaustralia.edu.au/courses/aur30320-certificate-iii-in-automotive-electrical-technology/#entryRequirements"
    data = {
        "url": url,
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "cricos_course_code": "",
        "apply_form": "https://vet.apexaustralia.edu.au"
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=90000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === COURSE DESCRIPTION ===
        desc_start = soup.select_one("#desBlock")
        if desc_start:
            desc_html = []
            for sib in desc_start.find_all_next():
                if sib.name == "h2" and sib.get("id") != "desBlock":
                    break
                if sib.name == "p":
                    desc_html.append(str(sib))
            data["course_description"] = clean_html(" ".join(desc_html))

        # === COURSE DURATION ===
        dur_block = soup.find("h3", string=re.compile("Duration", re.I))
        if dur_block and dur_block.find_parent("div", class_="det-box"):
            dur_div = dur_block.find_parent("div", class_="det-box")
            dur_text = dur_div.get_text(" ", strip=True)
            dur_match = re.search(r"(\d+\s*weeks?)", dur_text, re.I)
            if dur_match:
                data["total_course_duration"] = dur_match.group(1)

        # === COURSE FEES ===
        fee_block = soup.find("h3", string=re.compile("Fee", re.I))
        if fee_block and fee_block.find_parent("div", class_="det-box"):
            fee_html = fee_block.find_parent("div", class_="det-box").get_text(" ", strip=True)
            fees = [int(f.replace(",", "")) for f in re.findall(r"\$([\d,]+)", fee_html)]
            if fees:
                data["offshore_tuition_fee"] = str(max(fees))

        # === ENTRY REQUIREMENTS ===
        entry_h2 = soup.select_one("#entryRequirements")
        if entry_h2:
            entry_html = []
            for sib in entry_h2.find_all_next():
                if sib.name == "h2":
                    break
                if sib.name == "p":
                    entry_html.append(str(sib))
            data["entry_requirements"] = clean_html(" ".join(entry_html))

        # === CRICOS CODE ===
        crs = soup.select_one(".crcsCode span")
        if crs:
            data["cricos_course_code"] = crs.get_text(strip=True)

        await browser.close()

    # === SQL OUTPUT ===
    sql = f"""
UPDATE courses SET
    course_description = '{data["course_description"]}',
    total_course_duration = '{data["total_course_duration"]}',
    offshore_tuition_fee = '{data["offshore_tuition_fee"]}',
    entry_requirements = '{data["entry_requirements"]}',
    created_at = NOW(),
    updated_at = NOW(),
    apply_form = '{data["apply_form"]}'
WHERE cricos_course_code = '{data["cricos_course_code"]}';
"""
    print(sql)

asyncio.run(scrape_apex())
