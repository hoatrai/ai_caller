import os, httpx
from dotenv import load_dotenv
load_dotenv()
H = {"Authorization": f"Bearer {os.getenv('FISH_API_KEY')}"}
allv = {}
for sort in ("score", "task_count", "created_at"):
    n0 = len(allv)
    for page in range(1, 201):
        r = httpx.get("https://api.fish.audio/model", headers=H, timeout=30,
                      params={"language": "vi", "page_size": 50, "page_number": page, "sort_by": sort})
        r.raise_for_status()
        got = r.json().get("items", [])
        for it in got:
            allv[it["_id"]] = it
        if len(got) < 50:
            break
    print(f"{sort}: +{len(allv) - n0} mới, tổng {len(allv)}", flush=True)
