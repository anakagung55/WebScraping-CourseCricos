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


async def scrape_vit(url):
    data = {
        "url": url,
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "cricos_course_code": "",
        "apply_form": "https://vit.edu.au/apply-now"
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        print(f"🌐 Opening {url}")
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === DESCRIPTION ===
        desc_section = soup.find("div", class_="section-title")
        if desc_section:
            desc_html = []
            for tag in desc_section.find_all_next(["p"]):
                if tag.find_parent("table"):  # stop sebelum tabel course info
                    break
                desc_html.append(str(tag))
            data["course_description"] = clean_html(" ".join(desc_html))
        else:
            print("⚠️ No description found")

        # === TABLE INFO ===
        rows = soup.select("table.course-info-table tr")
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            label = tds[0].get_text(strip=True).lower()
            value_html = str(tds[2])
            value_text = tds[2].get_text(strip=True)

            if "cricos" in label:
                data["cricos_course_code"] = value_text
            elif "duration" in label:
                data["total_course_duration"] = value_text
            elif "entry" in label:
                data["entry_requirements"] = clean_html(value_html)

        # === FEE ===
        fee_div = soup.find(lambda tag: tag.name in ["ul", "li", "p", "div", "span"] and "$" in tag.get_text())
        if fee_div:
            data["offshore_tuition_fee"] = extract_fee_value(fee_div.get_text())
        else:
            print("⚠️ No fee found")


        await browser.close()

    return data


# === TEST RUN ===
url = "https://vit.edu.au/vocational/sit30821-certificate-iii-in-commercial-cookery"
result = asyncio.run(scrape_vit(url))

print("\n=== RESULT ===")
for k, v in result.items():
    print(f"{k}: {v[:400]}...\n" if isinstance(v, str) else f"{k}: {v}")
