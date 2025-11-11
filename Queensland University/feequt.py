import re

input_file = "Queensland University/qut_scraped_all_update_clean.sql"
output_file = "qut_offshore_fee_only.sql"

with open(input_file, "r", encoding="utf-8") as f:
    sql_text = f.read()

# Pola regex untuk menangkap setiap blok UPDATE
pattern = re.compile(
    r"UPDATE courses SET.*?offshore_tuition_fee\s*=\s*'([^']*)'.*?cricos_course_code\s*=\s*'([^']*)';",
    re.DOTALL,
)

matches = pattern.findall(sql_text)

# Buat hasil baru hanya untuk kolom fee
result_lines = []
for fee, cricos in matches:
    line = f"UPDATE courses SET offshore_tuition_fee = '{fee}' WHERE cricos_course_code = '{cricos}';"
    result_lines.append(line)

# Simpan hasil ke file baru
with open(output_file, "w", encoding="utf-8") as f:
    f.write("\n".join(result_lines))

print(f"Done! Total {len(result_lines)} update statements written to {output_file}")
