import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

def extract_fee_value(html: str) -> str:
    m = re.search(r"\$([\d,]+)", html)
    return m.group(1).replace(",", "") if m else ""

async def scrape_federation(url):
    data = {
        "url": url,
        "course_description": "",
        "total_course_duration": "4 years",  # test manual dulu
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "cricos_course_code": "",
        "apply_form": "https://apply.federation.edu.au/"
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=90000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === DESCRIPTION ===
        desc_div = soup.select_one("div.wysiwyg.prose.line-clamp-14.overflow-hidden")
        if desc_div:
            data["course_description"] = clean_html(str(desc_div))

        # === FEE ===
        fee_div = soup.find(lambda tag: tag.name == "div" and "$" in tag.get_text())
        if fee_div:
            data["offshore_tuition_fee"] = extract_fee_value(fee_div.get_text())

        # === ENTRY REQUIREMENTS ===
        entry_h2 = soup.find("h2", string=re.compile("Entry requirements", re.I))
        if entry_h2:
            parent_div = entry_h2.find_parent("div")
            if parent_div:
                data["entry_requirements"] = clean_html(str(parent_div))

        # === CRICOS ===
        cricos = ""
        for dd in soup.find_all("dd"):
            text = dd.get_text(strip=True)
            if re.match(r"^\d{6,7}[A-Za-z]$", text):
                cricos = text
                break
        data["cricos_course_code"] = cricos

        await browser.close()

    return data


# === TEST RUN ===
url = "https://www.federation.edu.au/courses/den8.mec-bachelor-of-engineering-mechanical-honours"
result = asyncio.run(scrape_federation(url))

print("\n=== RESULT ===")
for k, v in result.items():
    print(f"{k}: {v[:400]}...\n" if isinstance(v, str) else f"{k}: {v}")
