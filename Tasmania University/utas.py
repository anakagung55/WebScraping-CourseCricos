import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

def extract_fee_value(text: str) -> str:
    m = re.search(r"\$([\d,]+)", text)
    return m.group(1).replace(",", "") if m else ""

async def scrape_utas(url, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://apply.utas.edu.au",
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    try:
        await page.goto(url, timeout=120000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === COURSE NAME ===
        h1 = soup.find("h1")
        data["course_name"] = h1.get_text(strip=True) if h1 else ""

        # === COURSE DESCRIPTION ===
        desc_div = None
        for div in soup.select("div.richtext.richtext__medium"):
            if div.find("div", class_="lede"):
                desc_div = div
                break
        data["course_description"] = clean_html(str(desc_div)) if desc_div else ""

        # === DURATION ===
        dur = ""
        for span in soup.select("span.meta-list--item-inner"):
            text = span.get_text(" ", strip=True)
            if "Minimum" in text and "year" in text:
                # potong hanya sampai "years."
                match = re.search(r"^.*?years?\.", text)
                dur = match.group(0).strip() if match else text.strip()
                break
        data["total_course_duration"] = dur

        # === OFFSHORE TUITION FEE ===
        fee_val = ""
        fee_sections = soup.select("section.sectioned-content.int-sect.sectioned-content__tabular")
        for section in fee_sections:
            if re.search(r"International students", section.get_text(), re.I):
                fee_val = extract_fee_value(section.get_text())
                if fee_val:
                    break
        data["offshore_tuition_fee"] = fee_val

        # === ENTRY REQUIREMENTS ===
        entry_div = None
        for div in soup.select("div.accordion--content"):
            text = div.get_text(" ", strip=True)
            if re.search(r"All international students", text, re.I):
                entry_div = div
                break
        data["entry_requirements"] = clean_html(str(entry_div)) if entry_div else ""

        # === CRICOS ===
        cricos = ""
        full_text = soup.get_text(" ", strip=True)
        m = re.search(r"\b\d{6,7}[A-Za-z]?\b", full_text)
        if m:
            cricos = m.group(0)
        data["cricos_course_code"] = cricos

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")
    finally:
        await page.close()

    return data


async def main():
    df = pd.read_excel("utas.xlsx")
    all_data, sqls = [], []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        for i, row in enumerate(df.itertuples(), start=1):
            title = getattr(row, "title", "")
            url = getattr(row, "url", "")

            print(f"\n🔍 ({i}/{len(df)}) Scraping: {title}")
            result = await scrape_utas(url, browser)
            result["title"] = title
            all_data.append(result)

            cricos = result["cricos_course_code"] or "UNKNOWN"
            def esc(s): return s.replace("'", "''") if s else ""

            sql = (
                "UPDATE courses SET\n"
                f"course_description = '{esc(result['course_description'])}',\n"
                f"    total_course_duration = '{esc(result['total_course_duration'])}',\n"
                f"    offshore_tuition_fee = '{esc(result['offshore_tuition_fee'])}',\n"
                f"    entry_requirements = '{esc(result['entry_requirements'])}',\n"
                f"    apply_form = '{esc(result['apply_form'])}'\n"
                f"WHERE cricos_course_code = '{cricos}';"
            )
            sqls.append(sql)

            # Simpan progress tiap 10
            if i % 10 == 0:
                pd.DataFrame(all_data).to_excel("utas_scraped_progress.xlsx", index=False)
                with open("utas_scraped_progress.sql", "w", encoding="utf-8") as f:
                    f.write("\n\n".join(sqls))
                print(f"💾 Progress saved ({i}/{len(df)})")

        await browser.close()

    pd.DataFrame(all_data).to_excel("utas_scraped_all.xlsx", index=False)
    with open("utas_scraped_all.sql", "w", encoding="utf-8") as f:
        f.write("\n\n".join(sqls))

    print("\n✅ Done! Saved:\n- utas_scraped_all.xlsx\n- utas_scraped_all.sql")

if __name__ == "__main__":
    asyncio.run(main())
