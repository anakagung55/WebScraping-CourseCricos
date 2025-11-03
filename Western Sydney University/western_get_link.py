import requests
import pandas as pd

URL = "https://wsu-search.funnelback.squiz.cloud/s/search.json"
params = {
    "profile": "global",
    "query": "courses",
    "collection": "wsu~sp-search",
    "f.Tabs|2": "Courses",
    "num_ranks": 300,
    "start_rank": 1
}

r = requests.get(URL, params=params)
r.raise_for_status()
data = r.json()

# cek struktur
results = data["response"]["resultPacket"]["results"]

links = []
for item in results:
    url = item.get("liveUrl")
    if url and "future/study/courses" in url:
        links.append(url)

print(f"✅ Found {len(links)} course links")

# simpan hasil
pd.DataFrame(links, columns=["course_url"]).to_excel("wsu_course_links.xlsx", index=False)
with open("wsu_course_links.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(links))

print("📁 Saved: wsu_course_links.xlsx and wsu_course_links.txt")
