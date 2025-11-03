input_path = "deakin_scraped_all.sql"
output_path = "deakin_scraped_all_filtered.sql"

with open(input_path, "r", encoding="utf-8") as f:
    # pisah per blok UPDATE
    lines = f.read().split("UPDATE courses SET")

filtered_updates = []
for block in lines:
    if "WHERE cricos_course_code = 'UNKNOWN'" not in block and block.strip():
        # tambahkan newline setelah SET biar rapi
        cleaned_block = block.strip()
        if not cleaned_block.startswith("\n"):
            cleaned_block = "\n" + cleaned_block
        filtered_updates.append("UPDATE courses SET" + cleaned_block)

# pisahkan tiap blok dengan dua newline biar mudah dibaca
with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n\n".join(filtered_updates))

print(f"✅ Selesai! File hasil tersimpan di: {output_path}")

