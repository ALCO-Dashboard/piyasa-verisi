import re, requests, os, json
s = requests.Session(); s.headers.update({"User-Agent": "Mozilla/5.0"})
os.makedirs("out", exist_ok=True)
d = s.get("https://alco-dashboard.vercel.app/dashboard_data.json", timeout=90).json()
json.dump(d, open("out/alco.json", "w"), ensure_ascii=False)
def gez(o, yol=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if "swap" in k.lower(): print("KEY", yol + "/" + k, json.dumps(v, ensure_ascii=False)[:600])
            gez(v, yol + "/" + k)
    elif isinstance(o, list):
        for i, v in enumerate(o[:3]): gez(v, yol + f"[{i}]")
        if len(o) > 3: gez(o[-1], yol + "[-1]")
gez(d)
print("TOP", list(d.keys()), list(d.get("evds", {}).keys())[:200])
