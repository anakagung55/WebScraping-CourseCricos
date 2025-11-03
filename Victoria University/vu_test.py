import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    return html.strip()

# === ESCAPE SQL STRING ===
def esc_sql(s: str) -> str:
    if not s:
        return ""
    s = s.replace("'", "''")  # escape single quotes
    s = s.replace("\\", "\\\\")  # escape backslashes
    return s

# === EXTRACT FEE ===
def extract_fee(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"AU\$?([\d,]+)", text)
    if not m:
        return ""
    val = int(m.group(1).replace(",", "")) * 2
    return str(val)

# === SCRAPE SINGLE COURSE ===
async def scrape_vu(url, duration="", retry_domestic=True):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": duration,
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": "https://eaams.vu.edu.au/portal/Apply.aspx",
        "cricos_course_code": ""
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        print(f"\n🌐 Opening {url} ...")

        try:
            await page.goto(url, timeout=120000, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # === COURSE NAME ===
            h1 = soup.find("h1")
            data["course_name"] = h1.get_text(strip=True) if h1 else ""

            # === DESCRIPTION ===
            desc = soup.select_one("div#overview")
            data["course_description"] = clean_html(str(desc)) if desc else ""

            # === FEE ===
            fee_tag = soup.find("div", class_="vu-markup__inner", string=re.compile("AU"))
            if not fee_tag:
                fee_tag = soup.find("p", string=re.compile("AU"))
            if fee_tag:
                data["offshore_tuition_fee"] = extract_fee(fee_tag.get_text())

            # === ENTRY REQUIREMENTS ===
            entry = soup.select_one("div#entry-requirements")
            data["entry_requirements"] = clean_html(str(entry)) if entry else ""

            # === CRICOS CODE ===
            cricos = ""
            for s in soup.select("span.vu-course-each-basics-value"):
                text = s.get_text(strip=True)
                if re.match(r"^\d{6,7}[A-Za-z]?$", text):
                    cricos = text
                    break
            if not cricos:
                m = re.search(r"\b\d{6,7}[A-Z]?\b", soup.get_text())
                if m:
                    cricos = m.group(0)
            data["cricos_course_code"] = cricos

        except Exception as e:
            print(f"⚠️ Error scraping {url}: {e}")
        finally:
            await page.close()
            await browser.close()

    return data

# === TEST ONE URL ===
async def main():
    # contoh: MBA (Global)
    url = "https://www.vu.edu.au/courses/master-of-business-administration-global-bmag"
    duration = "2 years"

    result = await scrape_vu(url, duration)

    # tampilkan hasil singkat
    print("\n=== SCRAPED DATA ===")
    for k, v in result.items():
        print(f"{k}: {v[:200]}{'...' if len(v) > 200 else ''}")

    # buat SQL
    cricos = result["cricos_course_code"] or "UNKNOWN"
    sql = f"""UPDATE courses SET
    course_description = '{esc_sql(result["course_description"])}',
    total_course_duration = '{esc_sql(result["total_course_duration"])}',
    offshore_tuition_fee = '{esc_sql(result["offshore_tuition_fee"])}',
    entry_requirements = '{esc_sql(result["entry_requirements"])}',
    apply_form = '{esc_sql(result["apply_form"])}'
WHERE cricos_course_code = '{cricos}';
"""

    print("\n=== GENERATED SQL ===\n")
    print(sql)

    # simpan ke file
    with open("vu_test_output.sql", "w", encoding="utf-8") as f:
        f.write(sql)
    print("\n💾 Saved to vu_test_output.sql")

if __name__ == "__main__":
    asyncio.run(main())
