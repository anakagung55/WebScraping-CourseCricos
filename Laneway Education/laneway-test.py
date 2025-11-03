import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

async def scrape_laneway():
    url = "https://laneway.edu.au/certificate-iv-in-business/"
    data = {
        "url": url,
        "course_description": "",
        "cricos_course_code": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://laneway.edu.au"
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=90000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === DESCRIPTION ===
        desc_blocks = soup.select(".et_pb_column_1 .et_pb_text_inner")
        desc_html = ""

        if desc_blocks:
            # Ambil block terakhir di dalam kolom utama
            for block in reversed(desc_blocks):
                txt = block.get_text(" ", strip=True)
                # pastikan bukan banner kosong atau quote pendek
                if len(txt) > 50 and not re.search(r"‘|distracted|quote|banner", txt, re.IGNORECASE):
                    desc_html = clean_html(str(block))
                    break

        data["course_description"] = desc_html


        # === CRICOS & DURATION ===
        info_block = soup.select_one(".et_pb_blurb_description")
        if info_block:
            info_html = info_block.get_text(" ", strip=True)
            cricos_match = re.search(r"Cricos\s*Course\s*Code:\s*([A-Z0-9]+)", info_html, re.IGNORECASE)
            if cricos_match:
                data["cricos_course_code"] = cricos_match.group(1)
            dur_match = re.search(r"Duration:\s*([\d\s\w]+)", info_html, re.IGNORECASE)
            if dur_match:
                data["total_course_duration"] = dur_match.group(1).strip()

        # === ENTRY REQUIREMENTS ===
        # ambil block terakhir .et_pb_blurb_description (biasanya entry req)
        entry_blocks = soup.select(".et_pb_blurb_description")
        if entry_blocks:
            entry_html = clean_html(str(entry_blocks[-1]))
            data["entry_requirements"] = entry_html

        await browser.close()

    # === OUTPUT SQL ===
    if data["cricos_course_code"]:
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
    else:
        print("❌ CRICOS code not found")

asyncio.run(scrape_laneway())
