import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

async def scrape_laneway(url, browser):
    data = {
        "url": url,
        "course_description": "",
        "cricos_course_code": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://laneway.edu.au"
    }

    page = await browser.new_page()
    await page.goto(url, timeout=90000)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    # === DESCRIPTION ===
    desc_blocks = soup.select(".et_pb_column_1 .et_pb_text_inner")
    desc_html = ""
    if desc_blocks:
        for block in reversed(desc_blocks):
            txt = block.get_text(" ", strip=True)
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
    entry_blocks = soup.select(".et_pb_blurb_description")
    if entry_blocks:
        entry_html = clean_html(str(entry_blocks[-1]))
        data["entry_requirements"] = entry_html

    await page.close()
    return data


async def main():
    df = pd.read_excel("Laneway Education/laneway.xlsx")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results = []
        for _, row in df.iterrows():
            url = row["url"]
            print(f"Scraping {url} ...")
            res = await scrape_laneway(url, browser)
            results.append(res)
        await browser.close()

    # === OUTPUT SQL ===
    with open("laneway_output.sql", "w", encoding="utf-8") as f:
        for d in results:
            if d["cricos_course_code"]:
                sql = f"""
UPDATE courses SET
    course_description = '{d["course_description"]}',
    total_course_duration = '{d["total_course_duration"]}',
    offshore_tuition_fee = '{d["offshore_tuition_fee"]}',
    entry_requirements = '{d["entry_requirements"]}',
    created_at = NOW(),
    updated_at = NOW(),
    apply_form = '{d["apply_form"]}'
WHERE cricos_course_code = '{d["cricos_course_code"]}';
"""
                f.write(sql + "\n")
        print("\n✅ Done! Saved to laneway_output.sql")

asyncio.run(main())
