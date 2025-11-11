import re

# === PATH FILE ===
input_file = "Tasmania University/utas_scraped_all.sql"
output_file = "utas_entry_only.sql"

# === BACA FILE ===
with open(input_file, "r", encoding="utf-8") as f:
    sql_text = f.read()

# === PISAH SETIAP UPDATE STATEMENT ===
updates = re.split(r"(?=UPDATE courses\s+SET)", sql_text)

# === FILTER HANYA YANG ADA entry_requirements ===
filtered_updates = []
for block in updates:
    if "entry_requirements" in block:
        # Ambil hanya baris entry_requirements dan WHERE
        entry_part = re.search(
            r"entry_requirements\s*=\s*'(.*?)'\s*,?\s*WHERE\s+cricos_course_code\s*=\s*'([^']+)'",
            block,
            re.DOTALL,
        )
        if entry_part:
            entry_html = entry_part.group(1).strip()
            cricos = entry_part.group(2)
            clean_block = (
                "UPDATE courses\nSET\n    entry_requirements = '"
                + entry_html
                + "',\nWHERE\n    cricos_course_code = '"
                + cricos
                + "';\n"
            )
            filtered_updates.append(clean_block)

# === SIMPAN HASIL KE FILE BARU ===
with open(output_file, "w", encoding="utf-8") as f:
    f.write("\n\n".join(filtered_updates))

print(f"✅ Selesai! Total {len(filtered_updates)} entry ditemukan dan disimpan ke {output_file}")
