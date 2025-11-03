import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

def extract_fee_value(text: str) -> str:
    """ambil angka dolar pertama dan ubah jadi angka bersih"""
    m = re.search(r"\$\s*([\d,]+)", text)
    if not m:
        return ""
    return m.group(1).replace(",", "")

async def scrape_deakin(url, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "",
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    print(f"\n🌐 Opening {url} ...")

    try:
        await page.goto(url, timeout=120000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === Course Name ===
        h1 = soup.find("h1")
        data["course_name"] = h1.get_text(strip=True) if h1 else ""

        # === Course Description ===
        desc_section = soup.select_one('section#course-overview')
        data["course_description"] = clean_html(str(desc_section)) if desc_section else ""

        # === Duration ===
        keyfacts_section = soup.find("section", class_="content-box")
        duration = ""
        if keyfacts_section:
            dur_tag = keyfacts_section.find("h3", string=re.compile("Duration", re.I))
            if dur_tag:
                p_tag = dur_tag.find_next("p")
                duration = p_tag.get_text(strip=True) if p_tag else ""
        data["total_course_duration"] = duration

        # === Offshore Tuition Fee ===
        fee_section = soup.select_one("section#fees-and-scholarships")
        fee_val = ""
        if fee_section:
            text = fee_section.get_text(" ", strip=True)
            fee_val = extract_fee_value(text)
        data["offshore_tuition_fee"] = fee_val

        # === Entry Requirements (combine all section html from #entry-requirements until before fees) ===
        entry_html = ""
        entry_start = soup.select_one("section#entry-requirements")
        fee_section = soup.select_one("section#fees-and-scholarships")

        if entry_start and fee_section:
            collected = []
            for sib in entry_start.next_siblings:
                if sib == fee_section:
                    break
                if getattr(sib, "name", None) == "section":
                    collected.append(str(sib))
            entry_html = str(entry_start) + "".join(collected)
        elif entry_start:
            entry_html = str(entry_start)
        data["entry_requirements"] = clean_html(entry_html)

        # === Apply Form ===
        apply_link = ""
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "apply.deakin.edu.au" in href or "how-to-apply" in href:
                apply_link = href
                break
        data["apply_form"] = apply_link or "https://www.deakin.edu.au/study/how-to-apply"

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
    df = pd.read_excel("deakin.xlsx")
    all_data, sqls = [], []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        for i, row in enumerate(df.itertuples(), start=1):
            title = getattr(row, "title", "")
            url = getattr(row, "url", "")

            print(f"\n🔍 ({i}/{len(df)}) Scraping: {title}")
            result = await scrape_deakin(url, browser)
            result["title"] = title
            all_data.append(result)

            cricos = result["cricos_course_code"] or "UNKNOWN"
            def esc(s): return s.replace("'", "''") if s else ""

            sql = f"""
UPDATE courses SET
    course_description = '{esc(result["course_description"])}',
    total_course_duration = '{esc(result["total_course_duration"])}',
    offshore_tuition_fee = '{esc(result["offshore_tuition_fee"])}',
    entry_requirements = '{esc(result["entry_requirements"])}',
    apply_form = '{esc(result["apply_form"])}'
WHERE cricos_course_code = '{cricos}';
""".strip()
            sqls.append(sql)

            if i % 10 == 0:
                pd.DataFrame(all_data).to_excel("deakin_scraped_progress.xlsx", index=False)
                with open("deakin_scraped_progress.sql", "w", encoding="utf-8") as f:
                    f.write("\n\n".join(sqls))
                print(f"💾 Progress saved ({i}/{len(df)})")

        await browser.close()

    pd.DataFrame(all_data).to_excel("deakin_scraped_all.xlsx", index=False)
    with open("deakin_scraped_all.sql", "w", encoding="utf-8") as f:
        f.write("\n\n".join(sqls))

    print("\n✅ Done! Saved:\n- deakin_scraped_all.xlsx\n- deakin_scraped_all.sql")

if __name__ == "__main__":
    asyncio.run(main())
