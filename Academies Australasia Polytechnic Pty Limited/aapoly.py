# scrape_aapoly.py
# pip install playwright bs4 pandas lxml
# playwright install chromium

import re
import asyncio
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

EXCEL_PATH = "aapoly.xlsx"   # ganti bila perlu (contoh file: kolom 'title' dan 'url')
APPLY_FORM = "http://www.aapoly.edu.au/"

CRICOS_RE = re.compile(r"\b([0-9]{5,6}[A-Za-z]|[0-9]{7}[A-Za-z]?)\b", re.I)  # fleksibel, tapi kita ambil 7 char inti
CRICOS_7_RE = re.compile(r"\b([0-9]{6}[A-Za-z]|[0-9]{7})\b", re.I)            # prefer 7-char

def one_line_html(html: str) -> str:
    """Minify HTML (tanpa menghapus tag) agar aman di SQL satu baris."""
    if not html:
        return ""
    html = re.sub(r"\s+", " ", html)
    return html.strip()

def sql_escape(s: str) -> str:
    """Escape single quote untuk SQL string literal."""
    return s.replace("'", "''") if isinstance(s, str) else s

def extract_after_colon(text: str) -> str:
    parts = text.split(":", 1)
    return parts[1].strip() if len(parts) == 2 else text.strip()

def html_of(el) -> str:
    """Ambil innerHTML sebuah elemen BeautifulSoup."""
    if not el:
        return ""
    return "".join(str(c) for c in el.contents)

def pick_cricos(texts) -> str:
    joined = " ".join(texts)
    # Prioritaskan 7-char pattern
    m7 = CRICOS_7_RE.search(joined)
    if m7:
        return m7.group(1).upper()
    m = CRICOS_RE.search(joined)
    return m.group(1).upper() if m else ""

def normalize_fee_to_int(cost_text: str) -> int:
    # contoh input: "Cost: A$40,000" → 40000
    if not cost_text:
        return 0
    # ambil angka dengan koma
    m = re.search(r"([\d][\d,\.]*)", cost_text.replace("\u00A0", " "))
    if not m:
        return 0
    digits = re.sub(r"[^\d]", "", m.group(1))
    return int(digits) if digits.isdigit() else 0

def pick_description(soup: BeautifulSoup) -> str:
    """
    Description: dari block pertama yang relevan (sesuai contoh kamu: div.elementor-widget-container berisi <p>).
    Strategi: cari section/column elementor yang paling atas yang punya banyak <p>.
    """
    # Kandidat: semua container yang punya <p>
    cands = soup.select("div.elementor-widget-container")
    best = ""
    for c in cands:
        # heuristik: banyak <p> berturut
        ps = c.find_all("p")
        if len(ps) >= 2:  # deskripsi biasanya lebih dari 1 paragraf
            html = html_of(c)
            if len(html) > len(best):
                best = html
    return one_line_html(best)

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

    # fallback cricos kalau belum ketemu
    if not cricos:
        cricos = pick_cricos(texts)

    fee_int = normalize_fee_to_int(fee_text)
    return duration, fee_int, cricos

def pick_entry_requirements_full_html(soup: BeautifulSoup) -> str:
    """
    ENTRY (opsi B): Ambil HTML utuh di section 'Entry Requirements'.
    Strategi:
      - cari heading yang mengandung 'Entry Requirement'
      - ambil container dekatnya (widget/container/accordion) sebagai HTML utuh
    """
    # 1) cari elemen heading yang teksnya mengandung 'Entry Requirement'
    heading = None
    for tag in soup.find_all(True, string=re.compile(r"Entry\s*Requirements?", re.I)):
        heading = tag
        break

    if not heading:
        # Coba di anchor/aria-controls/tab label
        possible = soup.find(attrs={"id": re.compile(r"entry", re.I)})
        if possible:
            heading = possible

    # 2) Ambil blok konten setelah heading
    if heading:
        # coba parent besar section
        sec = heading
        # naik beberapa level sampai ketemu section elementor (heuristik)
        for _ in range(4):
            if sec and ("elementor-section" in (sec.get("class") or []) or "elementor-widget" in (sec.get("class") or [])):
                break
            sec = sec.parent if sec else None

        # Ambil saudara berikutnya yang biasanya berisi konten
        if sec and sec.next_sibling:
            sib = sec.next_sibling
            # jika NavigableString, iter sampai tag
            while hasattr(sib, "name") is False and sib is not None:
                sib = sib.next_sibling
            if getattr(sib, "name", None):
                return one_line_html(str(sib))

        # fallback: cari container setelah heading langsung
        container = heading.find_next("div", class_=re.compile(r"(elementor-widget|elementor-container|accordion|tab|panel)", re.I))
        if container:
            return one_line_html(str(container))

    # 3) fallback terakhir: cari semua paragraf/bullet yang berada di dekat kata Entry Requirements
    block = []
    anchor = soup.find(string=re.compile(r"Entry\s*Requirements?", re.I))
    if anchor:
        node = soup.find(text=anchor)
        # Ambil hingga 6 saudara berikut yang <p> atau <ul>/<ol>
        taken = 0
        cur = node.parent
        while cur and taken < 6:
            cur = cur.find_next_sibling()
            if not cur: break
            if cur.name in ("p", "ul", "ol", "div"):
                block.append(str(cur))
                taken += 1
        if block:
            return one_line_html("".join(block))
    return ""

async def fetch_course(url: str, browser) -> dict:
    page = await browser.new_page()
    await page.goto(url, timeout=90000)
    # beberapa halaman pakai lazy/tab – tunggu konten elementor muncul
    await page.wait_for_selector("body", timeout=90000)
    html = await page.content()
    soup = BeautifulSoup(html, "lxml")

    description_html = pick_description(soup)
    duration, fee_int, cricos = pick_duration_fee_cricos(soup)
    entry_html = pick_entry_requirements_full_html(soup)

    data = {
        "url": url,
        "course_description": description_html,
        "total_course_duration": duration,
        "offshore_tuition_fee": fee_int,
        "entry_requirements": entry_html,
        "cricos_course_code": cricos,
        "apply_form": APPLY_FORM,
    }
    await page.close()
    return data

def to_update_sql(row: dict) -> str:
    # Pastikan CRICOS ada (buat WHERE)
    cricos = row.get("cricos_course_code", "").strip()
    if not cricos:
        # kalau benar-benar tidak ada, pakai WHERE url sebagai fallback (opsional)
        where = f"WHERE url = '{sql_escape(row.get('url',''))}';"
    else:
        # Normalisasi ke 7 char (kalau ada spasi/variasi)
        m7 = CRICOS_7_RE.search(cricos)
        if m7:
            cricos = m7.group(1).upper()
        where = f"WHERE cricos_course_code = '{sql_escape(cricos)}';"

    url = sql_escape(row.get("url",""))
    desc = sql_escape(one_line_html(row.get("course_description","")))
    dur = sql_escape(row.get("total_course_duration",""))
    fee = row.get("offshore_tuition_fee", 0) or 0
    entry = sql_escape(one_line_html(row.get("entry_requirements","")))
    cricos_val = sql_escape(cricos)
    apply_form = sql_escape(row.get("apply_form",""))

    sql = f"""UPDATE courses
SET
    url = '{url}',
    course_description = '{desc}',
    total_course_duration = '{dur}',
    offshore_tuition_fee = {fee},
    entry_requirements = '{entry}',
    cricos_course_code = '{cricos_val}',
    apply_form = '{apply_form}'
{where}
"""
    return sql

async def main():
    df = pd.read_excel(EXCEL_PATH)
    if "url" not in df.columns:
        raise ValueError("Excel harus memiliki kolom 'url'. (kolom 'title' opsional)")
    urls = [u for u in df["url"].dropna().tolist() if isinstance(u, str) and u.strip()]

    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for url in urls:
            try:
                data = await fetch_course(url, browser)
            except Exception as e:
                # fallback minimal data saat gagal
                data = {
                    "url": url,
                    "course_description": "",
                    "total_course_duration": "",
                    "offshore_tuition_fee": 0,
                    "entry_requirements": "",
                    "cricos_course_code": "",
                    "apply_form": APPLY_FORM,
                }
                print(f"[WARN] Gagal scrape: {url} -> {e}")
            results.append(data)
        await browser.close()

    # Simpan SQL
    sqls = [to_update_sql(r) for r in results]
    with open("output.sql", "w", encoding="utf-8") as f:
        f.write(";\n".join(s.strip().rstrip(";") for s in sqls) + ";\n")

    # Opsional: export CSV hasil scrape
    pd.DataFrame(results).to_csv("aapoly_scraped.csv", index=False, encoding="utf-8")

if __name__ == "__main__":
    asyncio.run(main())
