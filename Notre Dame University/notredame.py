import re, asyncio, pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from playwright.async_api import async_playwright

def clean_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    html = html.replace("'", "''")  # aman SQL
    return html.strip()

def sanitize_html(soup: BeautifulSoup) -> str:
    """hapus elemen media dan ubah heading ke <p style='font-weight:bold;'>"""
    for tag in soup.find_all(['img', 'svg', 'picture', 'iframe', 'video', 'source']):
        tag.decompose()
    for h in soup.find_all(['h1', 'h2', 'h3']):
        h.name = 'p'
        h['style'] = 'font-weight:bold;'
    return str(soup)


async def scrape_notredame(url, browser):
    data = {
        "url": url,
        "course_name": "",
        "course_description": "",
        "total_course_duration": "",
        "offshore_tuition_fee": "",
        "entry_requirements": "",
        "apply_form": url,  # pakai url course
        "cricos_course_code": ""
    }

    page = await browser.new_page()
    try:
        await page.goto(url, timeout=90000, wait_until="domcontentloaded")

        # scroll untuk trigger lazy load
        for _ in range(15):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(0.6)
        await asyncio.sleep(2)

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === COURSE NAME ===
        h1 = soup.find("h1")
        data["course_name"] = h1.get_text(strip=True) if h1 else ""

        # === DESCRIPTION ===
        desc = soup.select_one("div.accordion__content[id^='Why_study_this_degree']")
        if desc:
            data["course_description"] = clean_html(sanitize_html(desc))

        # === ENTRY REQUIREMENTS ===
        entry = soup.select_one("div.accordion__content[id^='Entry_requirements']")
        if entry:
            data["entry_requirements"] = clean_html(sanitize_html(entry))

        # === DURATION & CRICOS ===
        pairs = await page.evaluate("""
            Array.from(document.querySelectorAll('li')).map(li => {
                const title = li.querySelector('.details-listing__title')?.textContent?.trim() || '';
                const value = li.querySelector('.details-listing__content')?.textContent?.trim() || '';
                return { title, value };
            });
        """)

        for p in pairs:
            title = (p.get("title") or "").lower()
            value = (p.get("value") or "").strip()
            if not value:
                continue

            if "duration" in title and not data["total_course_duration"]:
                data["total_course_duration"] = value
            if "cricos" in title and not data["cricos_course_code"]:
                data["cricos_course_code"] = value

        # === fallback ===
        if not data["total_course_duration"] or not data["cricos_course_code"]:
            runtime_spans = await page.evaluate("""
                Array.from(document.querySelectorAll('span.details-listing__content'))
                     .map(e => e.textContent.trim());
            """)
            if not data["total_course_duration"]:
                for t in runtime_spans:
                    if 'year' in t.lower() or 'full' in t.lower():
                        data["total_course_duration"] = t
                        break
            if not data["cricos_course_code"]:
                for t in runtime_spans:
                    s = t.strip().replace(" ", "")
                    if 7 <= len(s) <= 8 and s[:-1].isdigit():
                        data["cricos_course_code"] = s
                        break

    except Exception as e:
        print(f"⚠️ Error scraping {url}: {e}")
    finally:
        await page.close()

    return data


async def main():
    df = pd.read_excel("Notre Dame University/notredame.xlsx")
    all_data, sqls = [], []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        for i, row in enumerate(df.itertuples(), start=1):
            title = getattr(row, "title", "")
            url = getattr(row, "url", "")

            if not isinstance(url, str) or not url.startswith("http"):
                print(f"⚠️ Skipped invalid URL: {url}")
                continue

            print(f"\n🔍 ({i}/{len(df)}) Scraping: {title}")
            result = await scrape_notredame(url, browser)
            result["title"] = title

            if not result["course_name"]:
                print(f"⚠️ Skipped or failed: {title}")
                continue

            all_data.append(result)
            cricos = result["cricos_course_code"] or "UNKNOWN"

            def esc(s): return s.replace("'", "''") if s else ""

            sql = f"""
UPDATE courses SET
    course_description = '{esc(result["course_description"])}',
    total_course_duration = '{esc(result["total_course_duration"])}',
    offshore_tuition_fee = '{esc(result["offshore_tuition_fee"])}',
    entry_requirements = '{esc(result["entry_requirements"])}',
    apply_form = '{esc(result["apply_form"])}',
    created_at = '{now}',
    updated_at = '{now}'
WHERE cricos_course_code = '{cricos}';
"""
            sqls.append(sql)

            if i % 10 == 0:
                pd.DataFrame(all_data).to_excel("notredame_scraped_progress.xlsx", index=False)
                with open("notredame_scraped_progress.sql", "w", encoding="utf-8") as f:
                    f.write("\n".join(sqls))
                print(f"💾 Progress saved ({i}/{len(df)}) ...")

        await browser.close()

    pd.DataFrame(all_data).to_excel("notredame_scraped_all.xlsx", index=False)
    with open("notredame_scraped_all.sql", "w", encoding="utf-8") as f:
        f.write("\n".join(sqls))

    print("\n🎯 Done! Saved final outputs:")
    print("- notredame_scraped_all.xlsx")
    print("- notredame_scraped_all.sql")


if __name__ == "__main__":
    asyncio.run(main())
