import re, json, requests, io, os, sys, time
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA})
os.makedirs("out", exist_ok=True)
def kaydet(ad, t): open("out/" + ad, "w", encoding="utf-8").write(t)
# 1) ana sayfa ve JS paketlerinde API yolları
h = s.get("https://www.hmb.gov.tr/", timeout=60).text
kaydet("ana.html", h)
yollar = set()
for js in re.findall(r'src="([^"]+\.js)"', h):
    u = js if js.startswith("http") else "https://www.hmb.gov.tr" + js
    try:
        t = s.get(u, timeout=60).text
        yollar |= set(re.findall(r'["`/](portal/v2/[A-Za-z0-9_\-/?=&${}.]+)', t))
        kaydet("js_" + os.path.basename(u)[:60] + ".txt", "\n".join(sorted(set(re.findall(r'.{0,80}portal/v2.{0,120}', t)))))
    except Exception as e:
        print("js", u, e)
print("API yolları:", sorted(yollar))
# 2) kamu finansmanı istatistikleri sayfasındaki tüm dosyalar
t = s.get("https://www.hmb.gov.tr/portal/v2/pages?slug=kamu-finansmani-istatistikleri", timeout=90).text.replace("\\/", "/")
kaydet("kfi.json", t)
for u in sorted(set(re.findall(r"https://ms\.hmb\.gov\.tr/uploads/[^\"'\s<>]+", t))):
    print("DOSYA", u)
# 3) duyuru sayfası denemeleri
slug = "kasim-2026-ocak-2027-ic-borclanma-stratejisi"
for u in [f"https://www.hmb.gov.tr/portal/v2/pages?slug={slug}", f"https://www.hmb.gov.tr/portal/v2/pages?slug=duyuru/{slug}",
          f"https://www.hmb.gov.tr/portal/v2/announcements?slug={slug}", f"https://www.hmb.gov.tr/portal/v2/announcements/{slug}",
          f"https://www.hmb.gov.tr/portal/v2/duyuru?slug={slug}", f"https://www.hmb.gov.tr/portal/v2/news?slug={slug}",
          f"https://www.hmb.gov.tr/portal/v2/posts?slug={slug}", "https://www.hmb.gov.tr/portal/v2/announcements", "https://www.hmb.gov.tr/portal/v2/pages?slug=ic-borclanma-stratejisi",
          "https://www.hmb.gov.tr/portal/v2/pages?slug=borclanma-stratejisi", "https://www.hmb.gov.tr/portal/v2/pages?slug=ihale-takvimi", "https://www.hmb.gov.tr/portal/v2/pages?slug=ic-borclanma-ihale-takvimi"]:
    try:
        r = s.get(u, timeout=60); print("DENEME", r.status_code, len(r.text), u); kaydet("d_" + re.sub(r"\W+", "_", u[30:])[:80] + ".txt", r.text[:200000])
    except Exception as e:
        print("DENEME HATA", u, e)
    time.sleep(1)
