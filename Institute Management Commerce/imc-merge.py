import pandas as pd

# === BACA FILE ===
df_xlsx = pd.read_excel("imc.xlsx")
df_csv = pd.read_csv("imc-2025-10-29.csv")

# === NORMALISASI TITLE UNTUK MATCH ===
def norm(text):
    return str(text).strip().lower()

df_xlsx["title_norm"] = df_xlsx["title"].apply(norm)
df_csv["title_norm"] = df_csv["title"].apply(norm)

# === MERGE ===
merged = pd.merge(df_xlsx, df_csv, on="title_norm", how="left", suffixes=("", "_csv"))

# === PILIH KOLUM UTAMA ===
merged_final = merged[["title", "url", "cricos_code", "duration", "offshore_fee"]]

# === SIMPAN HASIL ===
merged_final.to_excel("imc_merged.xlsx", index=False)
print("✅ Done! Saved to imc_merged.xlsx")
