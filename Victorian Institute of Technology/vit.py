import re, asyncio, pandas as pd
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

async def scrape_vit(page, url):
    data = {
        "url": url,
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "cricos_course_code": "",
        "apply_form": "https://vit.edu.au/apply-now"
    }

    try:
        print(f"🌐 Scraping {url} ...")
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        soup = BeautifulSoup(await page.content(), "html.parser")

        # === DESCRIPTION ===
        desc_block = None
        blocks = soup.find_all("div", class_=re.compile(r"col-lg-12"))
        # cari blok yang mengandung kata Course Overview, atau paling panjang
        if blocks:
            for b in blocks:
                if "course overview" in b.get_text(" ", strip=True).lower():
                    desc_block = b
                    break
            if not desc_block:  # fallback ambil yg paling panjang (biasanya konten)
                desc_block = max(blocks, key=lambda x: len(x.get_text(strip=True)))

        if not desc_block:
            # fallback section
            desc_block = soup.find(lambda tag: tag.name == "section" and tag.find("h2") and tag.find("p"))

        if desc_block:
            data["course_description"] = clean_html(str(desc_block))
            print("✅ Description found")
        else:
            print("⚠️ No description found")

        # === TABLE INFO ===
        for tr in soup.select("table.course-info-table tr"):
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

        # === FALLBACK CRICOS & DURATION ===
        for p in soup.find_all("p"):
            text = p.get_text(" ", strip=True)
            if not data["cricos_course_code"] and re.search(r"cricos", text, re.I):
                m = re.search(r"([0-9]{6,7}[A-Za-z]?)", text)
                if m: data["cricos_course_code"] = m.group(1)
            if not data["total_course_duration"] and re.search(r"duration", text, re.I):
                m2 = re.search(r"([\d\-–]+ ?(?:week|year|month|semester|term)s?)", text, re.I)
                if m2: data["total_course_duration"] = m2.group(1)

        # === ENTRY FALLBACK ===
        if not data["entry_requirements"]:
            entry_div = soup.find(lambda t: t.name == "div" and re.search(r"(entry requirement|min.*english)", t.get_text(), re.I))
            if entry_div:
                data["entry_requirements"] = clean_html(str(entry_div))

        # === FEE ===
        fee_div = soup.find(lambda t: t.name in ["ul", "li", "p", "div", "span"] and "$" in t.get_text())
        if fee_div:
            data["offshore_tuition_fee"] = extract_fee_value(fee_div.get_text())

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")

    return data

# === MAIN ===
async def main():
    df = pd.read_excel("Victorian Institute of Technology/vit.xlsx")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i, row in df.iterrows():
            url = str(row.get("url", ""))
            if not url:
                continue
            print(f"\n[{i+1}/{len(df)}] {row.get('title','')}")
            data = await scrape_vit(page, url)
            results.append(data)

        await browser.close()

    def esc(t): return t.replace("'", "''") if t else ""

    sql = []
    for d in results:
        if not d["cricos_course_code"]:
            continue
        sql.append(f"""UPDATE courses SET
    course_description = '{esc(d["course_description"])}',
    total_course_duration = '{esc(d["total_course_duration"])}',
    offshore_tuition_fee = '{esc(d["offshore_tuition_fee"])}',
    entry_requirements = '{esc(d["entry_requirements"])}',
    apply_form = '{esc(d["apply_form"])}'
WHERE cricos_course_code = '{esc(d["cricos_course_code"])}';""")

    with open("vit_update.sql", "w", encoding="utf-8") as f:
        f.write("\n\n".join(sql))
    pd.DataFrame(results).to_excel("vit_result.xlsx", index=False)
    print("\n✅ Done. Saved vit_update.sql + vit_result.xlsx")

asyncio.run(main())
