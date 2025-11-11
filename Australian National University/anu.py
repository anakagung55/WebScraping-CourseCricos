from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup, NavigableString, Tag
import pandas as pd
import re, time, sys

# ====== CONFIG ======
INPUT_XLSX   = "Australian National University/study.xlsx"
OUTPUT_SQL   = "anu_courses_update.sql"
HEADLESS     = True
NAV_TIMEOUT  = 90000
POST_LOAD_MS = 3000
DELAY_BETWEEN = 0.4  # detik antar item

# ====== HELPERS ======
def esc(s: str) -> str:
    return s.replace("'", "''") if s else ""

def only_digits(s: str) -> str:
    if not s: return ""
    m = re.findall(r"[\d,\.]+", s)
    if not m: return ""
    # ambil angka pertama, buang koma & titik
    return re.sub(r"[^\d]", "", m[0])

def html_after_h2_until_next_h2(h2: Tag) -> str:
    """Ambil HTML setelah <h2> ini sampai ketemu <h2> berikutnya."""
    if not h2: return ""
    parts = []
    for sib in h2.next_siblings:
        if isinstance(sib, Tag) and sib.name == "h2":
            break
        if isinstance(sib, (Tag, NavigableString)):
            # keep only meaningful tags
            if isinstance(sib, Tag) and sib.name.lower() in {"p","ul","ol","li","div","strong","em","span"}:
                parts.append(str(sib))
            elif isinstance(sib, NavigableString):
                txt = sib.strip()
                if txt:
                    parts.append(txt)
    return "".join(parts).strip()

def get_cricos(soup: BeautifulSoup) -> str:
    # cari li yg heading-nya mengandung "CRICOS code"
    for li in soup.select("li.degree-summary__code"):
        head = li.select_one(".degree-summary__code-heading")
        if head and "cricos" in head.get_text(strip=True).lower():
            val = li.select_one(".degree-summary__code-text")
            return val.get_text(strip=True) if val else ""
    # fallback: cari label lain
    lbl = soup.find(string=re.compile(r"CRICOS", re.I))
    if lbl:
        # ambil angka/alfanumerik setelah label
        blk = lbl.find_parent()
        if blk:
            text = blk.get_text(" ", strip=True)
            m = re.search(r"CRICOS.*?([A-Z0-9]{6,10})", text, re.I)
            if m: return m.group(1)
    return ""

def parse_program_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # ===== DESCRIPTION =====
    # Ambil langsung seluruh HTML di dalam <div id="introduction">
    desc_div = soup.select_one("div#introduction")
    desc_html = str(desc_div).strip() if desc_div else ""

    # ===== ENTRY REQUIREMENTS =====
    entry_html = ""
    h2_adm = soup.select_one("h2#admission-requirements")
    if h2_adm:
        parts = []
        for sib in h2_adm.next_siblings:
            # stop ketika sudah ketemu section "Indicative fees"
            if isinstance(sib, Tag) and sib.get("id") == "indicative-fees":
                break
            # kumpulkan semua elemen antar Admission → Indicative fees
            if isinstance(sib, (Tag, NavigableString)):
                parts.append(str(sib))
        entry_html = "".join(parts).strip()

    # ===== OFFSHORE FEE =====
    fee_int_dd = soup.select_one("#indicative-fees__international dd")
    offshore_fee = only_digits(fee_int_dd.get_text(strip=True)) if fee_int_dd else ""

    # ===== CRICOS CODE =====
    cricos = get_cricos(soup)

    return {
        "course_description": esc(desc_html),
        "entry_requirements": esc(entry_html),
        "offshore_tuition_fee": offshore_fee,
        "cricos": cricos
    }


def sql_update_row(row: dict) -> str:
    return f"""UPDATE courses SET
    course_description = '{row["course_description"]}',
    onshore_tuition_fee = '',
    offshore_tuition_fee = '{row["offshore_tuition_fee"]}',
    entry_requirements = '{row["entry_requirements"]}',
    total_course_duration = '{esc(row["total_course_duration"])}',
    apply_form = '{esc(row["apply_form"])}'
    WHERE cricos_course_code = '{row["cricos"]}';"""

# ====== MAIN ======
def main():
    # baca excel
    try:
        df = pd.read_excel(INPUT_XLSX)
    except Exception as e:
        print(f"❌ Gagal baca {INPUT_XLSX}: {e}")
        sys.exit(1)

    # normalisasi nama kolom (hapus spasi dan tanda hubung)
    df.columns = (
        df.columns.str.strip()
        .str.replace(" ", "_")
        .str.replace("-", "_")
        .str.replace(r"__+", "_", regex=True)
        .str.lower()
    )

    # sekarang nama kolom berubah misalnya:
    # "acc-card-links href" → "acc_card_links_href"
    required_cols = [
        "acc_card_duration",
        "all_pc_apply_now_btn_href",
        "acc_card_links_href",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"❌ Kolom hilang di {INPUT_XLSX}: {missing}")
        print(f"Kolom tersedia: {list(df.columns)}")
        sys.exit(1)

    total = len(df)
    print(f"📄 Loaded {total} rows from {INPUT_XLSX}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page()

        written, skipped = 0, 0
        lines = []

        for i, r in enumerate(df.itertuples(index=False), start=1):
            url_detail   = getattr(r, "acc_card_links_href", "")
            duration     = getattr(r, "acc_card_duration", "")
            apply_link   = getattr(r, "all_pc_apply_now_btn_href", "")

            if not isinstance(url_detail, str) or not url_detail.startswith("http"):
                print(f"[{i}/{total}] ⚠️ Skip: URL tidak valid")
                skipped += 1
                continue

            try:
                print(f"[{i}/{total}] {url_detail}")
                page.goto(url_detail, timeout=NAV_TIMEOUT)
                page.wait_for_timeout(POST_LOAD_MS)

                parsed = parse_program_html(page.content())

                if not parsed["cricos"]:
                    print("   ⚠️ Tanpa CRICOS → skip (tidak bisa WHERE)")
                    skipped += 1
                    continue

                row_out = {
                    "course_description": parsed["course_description"],
                    "entry_requirements": parsed["entry_requirements"],
                    "offshore_tuition_fee": parsed["offshore_tuition_fee"],
                    "total_course_duration": duration,
                    "apply_form": apply_link,
                    "cricos": parsed["cricos"],
                }
                lines.append(sql_update_row(row_out))
                written += 1

            except Exception as e:
                print(f"   ❌ Error: {e}")
                skipped += 1
                continue

            time.sleep(DELAY_BETWEEN)

        browser.close()

    with open(OUTPUT_SQL, "w", encoding="utf-8") as f:
        f.write("\n\n".join(lines) + ("\n" if lines else ""))

    print(f"\n🎉 Done! SQL saved to {OUTPUT_SQL}")
    print(f"✅ Written: {written}   ⛔ Skipped: {skipped}")

if __name__ == "__main__":
    main()
