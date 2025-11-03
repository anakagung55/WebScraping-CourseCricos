from pathlib import Path
import re

input_file = "csu_update.sql"
output_file = "csu_update_clean.sql"

# Baca isi file
text = Path(input_file).read_text(encoding="utf-8")

# Pecah tiap query berdasarkan titik koma di akhir
queries = [q.strip() for q in re.split(r";\s*(?=UPDATE|\Z)", text, flags=re.IGNORECASE) if q.strip()]

# Simpan hanya query yang punya CRICOS code isi (bukan kosong)
filtered = [q + ";" for q in queries if not re.search(r"WHERE\s+cricos_course_code\s*=\s*''", q, flags=re.IGNORECASE)]

Path(output_file).write_text("\n\n".join(filtered), encoding="utf-8")

print(f"✅ Done. Queries with empty CRICOS removed. Saved as {output_file}")
print(f"💡 Remaining queries: {len(filtered)}")
