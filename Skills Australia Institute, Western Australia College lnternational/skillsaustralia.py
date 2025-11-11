import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    # normalize heading tags
    html = re.sub(r"<h[2-4][^>]*>", '<p style="font-weight: bold;">', html)
    html = re.sub(r"</h[2-4]>", "</p>", html)
    html = html.replace("'", "")  # remove single quotes for SQL safety
    return html.strip()

async def scrape_skills(url, browser):
    data = {
        "url": url,
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "cricos_course_code": "",
        "apply_form": url
    }

    page = await browser.new_page()
    await page.goto(url, timeout=90000)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    # === COURSE DESCRIPTION ===
    desc_block = soup.select_one("div#collapselp1 div.tab-content.cou-list-desc")
    if desc_block:
        desc_html = desc_block.decode_contents()
        data["course_description"] = clean_html(desc_html)

    # === ENTRY REQUIREMENTS ===
    entry_section = soup.find("div", class_="cou-over-head", string=re.compile("Entry Requirements", re.I))
    if entry_section:
        entry_block = entry_section.find_next("div", class_="descriptionblock")
        if entry_block:
            entry_html = entry_block.decode_contents()
            data["entry_requirements"] = clean_html(entry_html)

    # === DURATION ===
    dur_div = soup.find("div", class_="innertopcou-subcontnt")
    if dur_div:
        dur_text = dur_div.get_text(strip=True)
        dur_match = re.search(r"(\d+\s*Weeks?)", dur_text, re.I)
        if dur_match:
            data["total_course_duration"] = dur_match.group(1)

    # === CRICOS CODE ===
    cricos_code = ""
    for span in soup.find_all("span"):
        text = span.get_text(strip=True)
        # only capture valid course CRICOS (exclude provider 03548F)
        if re.fullmatch(r"\d{6,7}[A-Z]", text) and text != "03548F":
            cricos_code = text
            break
    data["cricos_course_code"] = cricos_code

    await page.close()

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
    print(f"✅ Scraped: {url}")
    return sql


async def main():
    df = pd.read_excel("skillsaustralia.xlsx")  # file dengan kolom 'url'
    urls = df["url"].dropna().tolist()

    sql_list = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for url in urls:
            try:
                query = await scrape_skills(url, browser)
                sql_list.append(query)
            except Exception as e:
                print(f"[ERROR] {url}: {e}")
        await browser.close()

    # === SAVE ALL SQL TO FILE ===
    with open("skills_output.sql", "w", encoding="utf-8") as f:
        f.write("\n".join(sql_list))

    print("\n🎉 All done! Queries saved to skills_output.sql")


if __name__ == "__main__":
    asyncio.run(main())
