import re, asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# === CLEAN HTML ===
def clean_html(html: str) -> str:
    """Rapikan HTML tapi biarkan tag utuh"""
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r"(<br\s*/?>\s*){2,}", "<br>", html)
    return html.strip()

async def scrape_canberra(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        print(f"\n🌐 Opening {url} ...")

        await page.goto(url, timeout=120000, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # === Click International Students Tab ===
        try:
            await page.click("text=International students")
            print("🌎 Clicked International Students tab")
        except:
            pass

        # === Wait until $ appears (for fee rendering) ===
        try:
            await page.wait_for_function("() => document.body.innerText.includes('$')", timeout=15000)
            print("💰 Fee content loaded")
        except:
            print("⚠️ Fee text not detected")

        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # === DESCRIPTION ===
        desc_div = soup.select_one("div.course-details.section div.introduction")
        description = clean_html(str(desc_div)) if desc_div else ""

        # === DURATION ===
        duration = ""
        for td in soup.find_all("td"):
            text = td.get_text(strip=True)
            if "year" in text.lower():
                duration = text
                break

        # === FEE ===
        fee_raw = await page.evaluate(
            "() => document.querySelector('span.international-fee-value')?.innerText || ''"
        )
        fee_value = ""
        matches = re.findall(r"(\d{4}).*?\$([\d,]+)", fee_raw)
        if matches:
            fee_dict = {y: a.replace(",", "") for y, a in matches}
            if "2026" in fee_dict:
                fee_value = fee_dict["2026"]
            elif "2025" in fee_dict:
                fee_value = fee_dict["2025"]

        # === ENTRY REQUIREMENTS (fix: ambil div paling bawah sebelum credit arrangements) ===
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

        print("\n=== RESULT ===")
        print(f"🧾 Description: {description[:150]}...")
        print(f"📆 Duration: {duration}")
        print(f"💰 Fee Raw: {fee_raw}")
        print(f"💰 Fee Normalized: {fee_value}")
        print(f"📜 Entry HTML: {entry_requirements[:300]}...")
        print(f"🏷️ CRICOS: {cricos}")

        await browser.close()

asyncio.run(scrape_canberra("https://www.canberra.edu.au/course/364JA/2/2026"))
