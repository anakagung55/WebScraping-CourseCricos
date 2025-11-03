import pandas as pd
from fuzzywuzzy import process

df_courses = pd.read_excel("greenwich.xlsx")
df_cricos = pd.read_excel("greenwich_cricos.xlsx")

df_courses["cricos_code"] = ""

def normalize(text):
    if not isinstance(text, str):
        return ""
    return " ".join(text.lower().split())

df_courses["title_norm"] = df_courses["title"].apply(normalize)
df_cricos["course_name_norm"] = df_cricos["course_name"].apply(normalize)
df_cricos["vet_code_norm"] = df_cricos["vet_code"].astype(str).apply(normalize)

vet_dict = dict(zip(df_cricos["vet_code_norm"], df_cricos["cricos_code"]))

# Step 1: match VET code
for i, row in df_courses.iterrows():
    title = row["title_norm"]
    url = str(row["url"]).lower()
    found = None
    for vet, cricos in vet_dict.items():
        if vet and (vet in title or vet in url):
            found = cricos
            break
    if found:
        df_courses.at[i, "cricos_code"] = found

# Step 2: fuzzy match nama course
unmatched = df_courses[df_courses["cricos_code"] == ""]
for i, row in unmatched.iterrows():
    title = row["title_norm"]
    result = process.extractOne(title, df_cricos["course_name_norm"])
    if result:
        best_match, score, _ = result  # ✅ FIXED: ambil 3 value
        if score > 80:
            cricos = df_cricos.loc[df_cricos["course_name_norm"] == best_match, "cricos_code"].values[0]
            df_courses.at[i, "cricos_code"] = cricos

df_courses.drop(columns=["title_norm"], inplace=True)
df_courses.to_excel("greenwich_matched.xlsx", index=False)
print("✅ Done! Saved to greenwich_matched.xlsx")
