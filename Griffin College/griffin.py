import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_styles(soup):
    # Hapus semua atribut style di elemen apa pun
    for tag in soup.find_all(True):
        if "style" in tag.attrs:
            del tag.attrs["style"]
    return soup

def normalize_html(soup):
    soup = clean_styles(soup)

    # Hapus elemen tidak perlu
    for tag in soup.find_all(["img", "svg", "iframe"]):
        tag.decompose()

    # Ganti heading dengan <p style="font-weight: bold;">
    for h in soup.find_all(["h1","h2","h3","h4","h5","h6"]):
        new_p = soup.new_tag("p")
        new_p["style"] = "font-weight: bold;"
        new_p.string = h.get_text(strip=True)
        h.replace_with(new_p)

    html = str(soup)
    html = html.replace("'", "❛")
    html = re.sub(r"\s+", " ", html)
    return html.strip()

async def scrape_griffin(url, browser):
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
    text_all = soup.get_text(" ", strip=True)

    # === COURSE DESCRIPTION ===
    desc_candidates = soup.select(".article-body span[dir='ltr'], .article-body p, .article-body div")
    for c in desc_candidates:
        text = c.get_text(strip=True)
        if ("qualification" in text.lower() or "course" in text.lower()) and not any(x in text.lower() for x in ["contact", "phone", "email"]):
            data["course_description"] = normalize_html(c)
            break

    # === DURATION ===
    dur_match = re.search(r"(\d+\s*weeks?)", text_all, re.I)
    if dur_match:
        data["total_course_duration"] = dur_match.group(1)

    # === FEE ===
    fee_match = re.search(r"A\$ ?([\d,]+)", text_all)
    if fee_match:
        data["offshore_tuition_fee"] = fee_match.group(1).replace(",", "")

    # === ENTRY REQUIREMENTS ===
    entry_start = soup.find("h4", id=lambda x: x and "ENTRY-REQUIREMENTS" in x)
    entry_end = soup.find("h4", id=lambda x: x and x.startswith("To-ensure-student"))

    if entry_start and entry_end:
        parts = []
        cur = entry_start
        while cur and cur != entry_end:
            parts.append(cur)
            cur = cur.find_next_sibling()
        parts.append(entry_end)

        entry_html = "".join(str(x) for x in parts)
        entry_html = re.sub(r'style="[^"]*"', "", entry_html)  # hapus inline style
        data["entry_requirements"] = normalize_html(BeautifulSoup(entry_html, "html.parser"))


    # === CRICOS ===
    cricos = re.search(r"\b\d{6,7}[A-Z]\b", text_all)
    if cricos:
        data["cricos_course_code"] = cricos.group(0)

    await page.close()

    # === SQL safe ===
    def safe_sql(v): return v.replace("\n"," ").replace("\r"," ").strip() if v else ""

    sql = f"""
UPDATE courses SET
    course_description = '{safe_sql(data["course_description"])}',
    total_course_duration = '{safe_sql(data["total_course_duration"])}',
    offshore_tuition_fee = '{safe_sql(data["offshore_tuition_fee"])}',
    entry_requirements = '{safe_sql(data["entry_requirements"])}',
    created_at = NOW(),
    updated_at = NOW(),
    apply_form = '{data["apply_form"]}'
WHERE cricos_course_code = '{safe_sql(data["cricos_course_code"])}';
"""
    print(f"✅ Scraped: {url}")
    return sql


async def main():
    df = pd.read_excel("griffin.xlsx")
    urls = df["url"].dropna().tolist()
    sql_list = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for url in urls:
            try:
                query = await scrape_griffin(url, browser)
                sql_list.append(query)
            except Exception as e:
                print(f"[ERROR] {url}: {e}")
        await browser.close()

    with open("griffin_output.sql", "w", encoding="utf-8") as f:
        f.write("\n".join(sql_list))

    print("\n🎉 Done! Saved as griffin_output.sql")

if __name__ == "__main__":
    asyncio.run(main())
