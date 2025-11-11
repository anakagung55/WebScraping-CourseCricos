import ssl, re, requests, pandas as pd, time
from bs4 import BeautifulSoup
from urllib3 import PoolManager
from requests.adapters import HTTPAdapter

# ==== SSL PATCH ====
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.options |= 0x4  # SSL_OP_LEGACY_SERVER_CONNECT
        self.poolmanager = PoolManager(*args, ssl_context=ctx, **kwargs)

session = requests.Session()
session.mount("https://", SSLAdapter())

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Referer": "https://www.adelaide.edu.au/degree-finder/all",
}

# === READ URLS FROM FILE ===
with open("The University Of Adelaide/adelaide_links.txt", "r", encoding="utf-8") as f:
    urls = [line.strip() for line in f if line.strip()]

results = []
error_log = []

def auto_save(progress_num):
    df = pd.DataFrame(results)
    df.to_excel("adelaide_update_partial.xlsx", index=False)
    with open("adelaide_update_partial.sql", "w", encoding="utf-8") as f:
        for row in results:
            f.write(row["sql"] + "\n\n")
    print(f"💾 Auto-saved after {progress_num} records ✅")


for i, url in enumerate(urls, 1):
    print(f"\n[{i}/{len(urls)}] Scraping: {url}")
    try:
        r = session.get(url, headers=headers, timeout=40, allow_redirects=False)
        html = r.text
        if not html.strip():
            print("⚠️ Empty body — skipped.")
            continue

        soup = BeautifulSoup(html, "html.parser")

        # === 1️⃣ Course Description ===
        desc_div = soup.find("div", class_="intro-df")
        course_description = str(desc_div) if desc_div else ""

        # === 2️⃣ Entry Requirements ===
        entry_requirements = ""
        entry_div = soup.find("div", id=re.compile(r"entry[-_ ]requirements", re.I))
        if not entry_div:
            entry_div = soup.find("div", class_=re.compile(r"df_ent_req", re.I))
        if not entry_div:
            entry_h2 = soup.find("h2", string=re.compile(r"Entry\s*Requirements", re.I))
            if entry_h2:
                entry_div = entry_h2.find_parent("div")
        if not entry_div:
            html_str = str(soup)
            match = re.search(
                r'(<div[^>]*Entry[^>]*Requirements[^>]*>.*?</div>)',
                html_str,
                re.I | re.S
            )
            if match:
                entry_requirements = match.group(1)
        if entry_div and not entry_requirements:
            entry_requirements = str(entry_div)

        # === 3️⃣ Duration ===
        total_course_duration = ""
        for box in soup.select("div.c-icon-box__content"):
            head = box.find("h3")
            if head and "Duration" in head.get_text():
                total_course_duration = box.get_text(" ", strip=True)
                total_course_duration = re.sub(r"\s+", " ", total_course_duration)
                break

        # === 4️⃣ Tuition Fees ===
        onshore_tuition_fee = ""
        offshore_tuition_fee = ""
        page_text = soup.get_text(" ", strip=True)

        m_dom = re.search(r"Commonwealth[- ]supported place[: ]*\$[\d,]+", page_text, re.I)
        if m_dom:
            onshore_tuition_fee = re.search(r"\$[\d,]+", m_dom.group(0)).group(0).replace("$", "").replace(",", "")

        m_int = re.search(r"International student place[: ]*\$[\d,]+", page_text, re.I)
        if m_int:
            offshore_tuition_fee = re.search(r"\$[\d,]+", m_int.group(0)).group(0).replace("$", "").replace(",", "")

        if not offshore_tuition_fee:
            all_fees = [int(x.replace("$", "").replace(",", "")) for x in re.findall(r"\$[\d,]+", page_text)]
            if all_fees:
                offshore_tuition_fee = str(max(all_fees))

        # === 5️⃣ Apply Form (diubah agar langsung ke link course) ===
        apply_form = url  # ✅ langsung isi dengan link course

        # === 6️⃣ CRICOS ===
        cricos_td = soup.find("td", attrs={"data-th": "CRICOS"})
        cricos = cricos_td.get_text(strip=True) if cricos_td else ""

        # === 7️⃣ Build SQL (tambahkan created_at & updated_at) ===
        sql = f"""UPDATE courses SET
    course_description = {repr(course_description)},
    onshore_tuition_fee = '{onshore_tuition_fee}',
    offshore_tuition_fee = '{offshore_tuition_fee}',
    entry_requirements = {repr(entry_requirements)},
    total_course_duration = '{total_course_duration}',
    apply_form = '{apply_form}',
    created_at = NOW(),
    updated_at = NOW()
WHERE cricos_course_code = '{cricos}';"""

        results.append({
            "url": url,
            "cricos_course_code": cricos,
            "onshore_tuition_fee": onshore_tuition_fee,
            "offshore_tuition_fee": offshore_tuition_fee,
            "total_course_duration": total_course_duration,
            "apply_form": apply_form,
            "sql": sql
        })

        print(f"✅ Done: CRICOS={cricos or 'N/A'} | Fees=({onshore_tuition_fee}/{offshore_tuition_fee})")

        if i % 10 == 0:
            auto_save(i)

        time.sleep(1.2)

    except Exception as e:
        print(f"❌ Error at {url}: {e}")
        error_log.append({"url": url, "error": str(e)})
        if i % 10 == 0:
            auto_save(i)
        continue

# === FINAL SAVE ===
pd.DataFrame(results).to_excel("adelaide_update.xlsx", index=False)
with open("adelaide_update.sql", "w", encoding="utf-8") as f:
    for row in results:
        f.write(row["sql"] + "\n\n")

if error_log:
    pd.DataFrame(error_log).to_excel("adelaide_errors.xlsx", index=False)

print("\n🎉 DONE! Saved all results:")
print("→ adelaide_update.xlsx (full results)")
print("→ adelaide_update.sql (SQL queries)")
if error_log:
    print("→ adelaide_errors.xlsx (log error)")
