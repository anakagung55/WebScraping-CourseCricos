import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

# === EXTRACT FEE VALUE ===
def extract_fee_value(html: str) -> str:
    """Cari fee tahun 2026, fallback ke 2025"""
    m26 = re.search(r"2026.*?\$([\d,]+)", html)
    m25 = re.search(r"2025.*?\$([\d,]+)", html)
    if m26:
        return m26.group(1).replace(",", "")
    elif m25:
        return m25.group(1).replace(",", "")
    return ""

# === SCRAPER FUNGSI PER COURSE ===
async def scrape_canberra(url, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://www.canberra.edu.au/apply",
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    try:
        await page.goto(url, timeout=120000, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Tunggu fee render (biar gak kosong)
        try:
            await page.wait_for_selector("span.international-fee-value", timeout=10000)
        except:
            print("⚠️ Fee section not loaded, continuing anyway...")

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === COURSE NAME ===
        h1 = soup.find("h1")
        data["course_name"] = h1.get_text(strip=True) if h1 else ""

        # === COURSE DESCRIPTION ===
        intro = None
        for div in soup.select("div.course-details.section"):
            if div.find("div", class_="introduction"):
                intro = div
                break
        data["course_description"] = clean_html(str(intro)) if intro else ""

        # === DURATION ===
        dur = ""
        for td in soup.find_all("td"):
            text = td.get_text(strip=True)
            if "year" in text.lower():
                dur = text
                break
        data["total_course_duration"] = dur

        # === OFFSHORE TUITION FEE ===
        fee_html = ""
        fee_tag = soup.select_one("span.international-fee-value")
        if fee_tag:
            fee_html = str(fee_tag)
        else:
            # fallback: ambil dari hidden input (biasanya id='9-eftsl-international')
            fee_input = soup.find("input", id=re.compile(r"\d+-eftsl-international"))
            if fee_input and fee_input.get("value"):
                fee_html = "$" + fee_input["value"]
        data["offshore_tuition_fee"] = extract_fee_value(fee_html)

        # === ENTRY REQUIREMENTS ===
        entry_html = ""
        try:
            target_div = soup.select_one("div.assumed-knowledge-collapse.px-5.py-3.collapse.show")
            if target_div:
                entry_html = str(target_div)
            else:
                # fallback: cari div dengan id yang mengandung 'accordion' dan class 'assumed-knowledge-collapse'
                for div in soup.find_all("div", class_=re.compile(r"assumed-knowledge-collapse")):
                    entry_html = str(div)
                    break
        except Exception as e:
            print(f"⚠️ Failed extracting entry requirements: {e}")

        data["entry_requirements"] = clean_html(entry_html)


        # === CRICOS ===
        cricos = ""
        for td in soup.find_all("td"):
            text = td.get_text(strip=True)
            if re.match(r"^\d{6,7}[A-Za-z]$", text):
                cricos = text
                break
        data["cricos_course_code"] = cricos

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")
    finally:
        await page.close()

    return data

# === MAIN LOOP ===
async def main():
    df = pd.read_excel("canberra.xlsx")
    all_data, sqls = [], []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        for i, row in enumerate(df.itertuples(), start=1):
            title = getattr(row, "title", "")
            url = getattr(row, "url", "")

            print(f"\n🔍 ({i}/{len(df)}) Scraping: {title}")
            result = await scrape_canberra(url, browser)
            result["title"] = title
            all_data.append(result)

            cricos = result["cricos_course_code"] or "UNKNOWN"
            def esc(s): return s.replace("'", "''") if s else ""

            sql = (
                "UPDATE courses SET\n"
                f"    course_description = '{esc(result['course_description'])}',\n"
                f"    total_course_duration = '{esc(result['total_course_duration'])}',\n"
                f"    offshore_tuition_fee = '{esc(result['offshore_tuition_fee'])}',\n"
                f"    entry_requirements = '{esc(result['entry_requirements'])}',\n"
                f"    apply_form = '{esc(result['apply_form'])}'\n"
                f"WHERE cricos_course_code = '{cricos}';"
            )
            sqls.append(sql)

            # save tiap 10 progress
            if i % 10 == 0:
                pd.DataFrame(all_data).to_excel("canberra_scraped_progress.xlsx", index=False)
                with open("canberra_scraped_progress.sql", "w", encoding="utf-8") as f:
                    f.write("\n\n".join(sqls))
                print(f"💾 Progress saved ({i}/{len(df)})")

        await browser.close()

    pd.DataFrame(all_data).to_excel("canberra_scraped_all.xlsx", index=False)
    with open("canberra_scraped_all.sql", "w", encoding="utf-8") as f:
        f.write("\n\n".join(sqls))

    print("\n✅ Done! Saved:\n- canberra_scraped_all.xlsx\n- canberra_scraped_all.sql")


if __name__ == "__main__":
    asyncio.run(main())
