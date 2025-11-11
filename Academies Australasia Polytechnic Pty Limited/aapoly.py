# scrape_aapoly_final.py

import re
import asyncio
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from playwright.async_api import async_playwright

EXCEL_PATH = "Academies Australasia Polytechnic Pty Limited/aapoly.xlsx"
APPLY_FORM_DEFAULT = "http://www.aapoly.edu.au/"

CRICOS_RE = re.compile(r"\b([0-9]{5,6}[A-Za-z]|[0-9]{7}[A-Za-z]?)\b", re.I)
CRICOS_7_RE = re.compile(r"\b([0-9]{6}[A-Za-z]|[0-9]{7})\b", re.I)

# === HELPER FUNGSI UMUM ===
def one_line_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

def sql_escape(s: str) -> str:
    return s.replace("'", "''") if isinstance(s, str) else s

def sanitize_html(soup: BeautifulSoup) -> str:
    """hapus elemen visual dan ubah heading jadi <p style='font-weight:bold;'>"""
    for tag in soup.find_all(['img', 'svg', 'iframe', 'video', 'picture', 'source']):
        tag.decompose()
    for h in soup.find_all(['h1', 'h2', 'h3']):
        h.name = 'p'
        h['style'] = 'font-weight:bold;'
    return str(soup)

def extract_after_colon(text: str) -> str:
    parts = text.split(":", 1)
    return parts[1].strip() if len(parts) == 2 else text.strip()

def html_of(el) -> str:
    if not el:
        return ""
    return "".join(str(c) for c in el.contents)

def pick_cricos(texts) -> str:
    joined = " ".join(texts)
    m7 = CRICOS_7_RE.search(joined)
    if m7:
        return m7.group(1).upper()
    m = CRICOS_RE.search(joined)
    return m.group(1).upper() if m else ""

def normalize_fee_to_int(cost_text: str) -> int:
    if not cost_text:
        return 0
    m = re.search(r"([\d][\d,\.]*)", cost_text.replace("\u00A0", " "))
    if not m:
        return 0
    digits = re.sub(r"[^\d]", "", m.group(1))
    return int(digits) if digits.isdigit() else 0

# === DESCRIPTION ===
def pick_description(soup: BeautifulSoup) -> str:
    cands = soup.select("div.elementor-widget-container")
    best = ""
    for c in cands:
        ps = c.find_all("p")
        if len(ps) >= 2:
            html = html_of(c)
            if len(html) > len(best):
                best = html
    if best:
        soup_best = BeautifulSoup(best, "lxml")
        return one_line_html(sanitize_html(soup_best))
    return ""

def pick_icon_list_texts(soup: BeautifulSoup):
    spans = soup.select("span.elementor-icon-list-text")
    texts = [s.get_text(" ", strip=True) for s in spans]
    return texts

def pick_duration_fee_cricos(soup: BeautifulSoup):
    texts = pick_icon_list_texts(soup)
    duration = ""
    fee_text = ""
    cricos = ""
    for t in texts:
        low = t.lower()
        if "duration" in low and not duration:
            duration = extract_after_colon(t)
        if ("cost" in low or "tuition" in low) and not fee_text:
            fee_text = extract_after_colon(t)
        if "cricos" in low and not cricos:
            cricos = pick_cricos([t])
    if not cricos:
        cricos = pick_cricos(texts)
    fee_int = normalize_fee_to_int(fee_text)
    return duration, fee_int, cricos

def pick_entry_requirements_full_html(soup: BeautifulSoup) -> str:
    heading = None
    for tag in soup.find_all(True, string=re.compile(r"Entry\s*Requirements?", re.I)):
        heading = tag
        break
    if not heading:
        possible = soup.find(attrs={"id": re.compile(r"entry", re.I)})
        if possible:
            heading = possible
    if heading:
        sec = heading
        for _ in range(4):
            if sec and ("elementor-section" in (sec.get("class") or []) or "elementor-widget" in (sec.get("class") or [])):
                break
            sec = sec.parent if sec else None
        if sec and sec.next_sibling:
            sib = sec.next_sibling
            while hasattr(sib, "name") is False and sib is not None:
                sib = sib.next_sibling
            if getattr(sib, "name", None):
                soup_sec = BeautifulSoup(str(sib), "lxml")
                return one_line_html(sanitize_html(soup_sec))
        container = heading.find_next("div", class_=re.compile(r"(elementor|accordion|tab|panel)", re.I))
        if container:
            soup_cont = BeautifulSoup(str(container), "lxml")
            return one_line_html(sanitize_html(soup_cont))
    block = []
    anchor = soup.find(string=re.compile(r"Entry\s*Requirements?", re.I))
    if anchor:
        node = soup.find(text=anchor)
        taken = 0
        cur = node.parent
        while cur and taken < 6:
            cur = cur.find_next_sibling()
            if not cur:
                break
            if cur.name in ("p", "ul", "ol", "div"):
                block.append(str(cur))
                taken += 1
        if block:
            soup_block = BeautifulSoup("".join(block), "lxml")
            return one_line_html(sanitize_html(soup_block))
    return ""

# === FETCH PER COURSE ===
async def fetch_course(url: str, browser) -> dict:
    page = await browser.new_page()
    await page.goto(url, timeout=90000)
    await page.wait_for_selector("body", timeout=90000)
    html = await page.content()
    soup = BeautifulSoup(html, "lxml")

    description_html = pick_description(soup)
    duration, fee_int, cricos = pick_duration_fee_cricos(soup)
    entry_html = pick_entry_requirements_full_html(soup)

    data = {
        "course_description": description_html,
        "total_course_duration": duration,
        "offshore_tuition_fee": fee_int,
        "entry_requirements": entry_html,
        "cricos_course_code": cricos,
        "apply_form": url,  # langsung ke course URL
    }
    await page.close()
    return data

# === SQL OUTPUT ===
def to_update_sql(row: dict, now: str) -> str:
    cricos = row.get("cricos_course_code", "").strip()
    if not cricos:
        where = f"WHERE url = '{sql_escape(row.get('url',''))}';"
    else:
        m7 = CRICOS_7_RE.search(cricos)
        if m7:
            cricos = m7.group(1).upper()
        where = f"WHERE cricos_course_code = '{sql_escape(cricos)}';"

    sql = f"""UPDATE courses SET
    course_description = '{sql_escape(one_line_html(row.get("course_description","")))}',
    total_course_duration = '{sql_escape(row.get("total_course_duration",""))}',
    offshore_tuition_fee = '{row.get("offshore_tuition_fee",0)}',
    entry_requirements = '{sql_escape(one_line_html(row.get("entry_requirements","")))}',
    apply_form = '{sql_escape(row.get("apply_form",""))}',
    updated_at = '{now}'
{where}
"""
    return sql.strip()

# === MAIN ===
async def main():
    df = pd.read_excel(EXCEL_PATH)
    urls = [u for u in df["url"].dropna().tolist() if isinstance(u, str) and u.strip()]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for url in urls:
            try:
                data = await fetch_course(url, browser)
            except Exception as e:
                data = {
                    "url": url,
                    "course_description": "",
                    "total_course_duration": "",
                    "offshore_tuition_fee": 0,
                    "entry_requirements": "",
                    "cricos_course_code": "",
                    "apply_form": APPLY_FORM_DEFAULT,
                }
                print(f"[WARN] Gagal scrape: {url} -> {e}")
            results.append(data)
        await browser.close()

    sqls = [to_update_sql(r, now) for r in results]
    with open("aapoly_update.sql", "w", encoding="utf-8") as f:
        f.write(";\n".join(s.strip().rstrip(";") for s in sqls) + ";\n")

    pd.DataFrame(results).to_csv("aapoly_scraped.csv", index=False, encoding="utf-8")
    print("\n🎯 Done! Saved -> aapoly_update.sql & aapoly_scraped.csv")

if __name__ == "__main__":
    asyncio.run(main())
