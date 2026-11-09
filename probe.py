import re, requests, os
s = requests.Session(); s.headers.update({"User-Agent": "Mozilla/5.0"})
os.makedirs("out", exist_ok=True)
B = "https://alco-dashboard.vercel.app"
h = s.get(B + "/", timeout=60).text
open("out/index.html", "w").write(h)
js = re.findall(r'(?:src|href)="([^"]+\.(?:js|mjs))"', h)
print("JS", js)
seen = set()
def al(u):
    u = u if u.startswith("http") else B + ("" if u.startswith("/") else "/") + u
    if u in seen: return
    seen.add(u)
    t = s.get(u, timeout=60).text
    open("out/" + re.sub(r"\W", "_", u[-80:]) + ".txt", "w").write(t)
    for m in re.findall(r'["\'`](/?assets/[^"\'`]+\.js)["\'`]', t):
        al(m)
for u in js: al(u)
tum = "\n".join(open("out/" + f).read() for f in os.listdir("out"))
print("URL", sorted(set(re.findall(r"https?://[A-Za-z0-9./_\-?=&%:]+", tum)))[:300])
print("API", sorted(set(re.findall(r'["\'`](/api/[^"\'`]+)["\'`]', tum))))
for k in ["yabanc", "Yabanc", "portf", "Portf", "TP.", "evds", "EVDS", "menkul", "swap", "Swap"]:
    for m in re.finditer(re.escape(k), tum):
        print("CTX", k, tum[max(0, m.start()-150):m.start()+150].replace("\n", " "))
        break
