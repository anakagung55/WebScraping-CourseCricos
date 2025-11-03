import re

input_path = "utas_scraped_all.sql"
output_path = "utas_scraped_all_filtered.sql"

with open(input_path, "r", encoding="utf-8") as f:
    content = f.read()

# Pisah setiap blok berdasarkan UPDATE courses SET
blocks = content.split("UPDATE courses SET")

unique = {}
for block in blocks:
    block = block.strip()
    if not block:
        continue

    # Pastikan ini blok valid (ada WHERE cricos)
    m = re.search(r"WHERE\s+cricos_course_code\s*=\s*'([^']+)'", block)
    if not m:
        continue

    cricos = m.group(1).strip()

    # skip UNKNOWN
    if cricos.upper() == "UNKNOWN":
        continue

    # simpan hanya yang pertama (hapus duplikat)
    if cricos not in unique:
        unique[cricos] = "UPDATE courses SET\n" + block

# tulis ulang hasil
with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n\n".join(unique.values()))

print(f"✅ Selesai! Hasil bersih disimpan di: {output_path}")
print(f"Total query unik tersisa: {len(unique)}")
