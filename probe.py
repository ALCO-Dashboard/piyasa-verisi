import re, json, requests, io, os, time
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA})
os.makedirs("out", exist_ok=True)
def kaydet(ad, t): open("out/" + ad, "w", encoding="utf-8").write(t)
# 1) iç borçlanma stratejisi duyuruları
for u in ["https://www.hmb.gov.tr/portal/v2/posts?search=borçlanma%20stratejisi&per_page=10&_fields=id,date,slug,title,content",
          "https://www.hmb.gov.tr/portal/v2/posts?categories=35&per_page=30&_fields=id,date,slug,title,content"]:
    r = s.get(u, timeout=60); print("POSTS", r.status_code, len(r.text), u); kaydet("posts_" + str(len(os.listdir("out"))) + ".json", r.text)
    time.sleep(1)
from pypdf import PdfReader
t = s.get("https://www.hmb.gov.tr/portal/v2/posts?search=borçlanma%20stratejisi&per_page=10&_fields=id,date,slug,title,content", timeout=60).json()
pdfs = []
for p in t:
    for u in re.findall(r'href="([^"]+\.pdf)"', p["content"]["rendered"]):
        pdfs.append((p["date"], p["slug"], u))
print("PDF", pdfs)
for i, (d, sl, u) in enumerate(pdfs[:3]):
    b = s.get(u, timeout=90).content
    open(f"out/strateji_{i}.pdf", "wb").write(b)
    try:
        R = PdfReader(io.BytesIO(b)); kaydet(f"strateji_{i}.txt", f"{d} {sl}\n" + "\n\f\n".join(pg.extract_text() or "" for pg in R.pages))
        kaydet(f"strateji_{i}_layout.txt", "\n\f\n".join(pg.extract_text(extraction_mode="layout") or "" for pg in R.pages))
    except Exception as e:
        print("pdf hata", e)
    time.sleep(1)
# 2) tarihçe dosyaları
import xlrd, openpyxl
kfi = s.get("https://www.hmb.gov.tr/portal/v2/pages?slug=kamu-finansmani-istatistikleri", timeout=90).text.replace("\\/", "/")
for desen in ["Doviz-Faiz_Yapisi", "Enstruman_Dagilimi", "Vadeye_Kalan_Ortalama_Suresi", "Merkezi_Yonetim_Dis_Borc_Stoku-", "Ic-Borclanmanin-Ortalama-Vadesi", "Ic-Borclanmanin-Ortalama-Maliyeti"]:
    m = re.findall(r"https://ms\.hmb\.gov\.tr/uploads/[^\"'\s<>]*" + re.escape(desen) + r"[^\"'\s<>]*\.xlsx?", kfi)
    if not m: print("YOK", desen); continue
    u = m[0]; b = s.get(u, timeout=120).content; print("İNDİ", u, len(b))
    out = []
    try:
        if u.endswith(".xls"):
            wb = xlrd.open_workbook(file_contents=b)
            for sh in wb.sheets():
                out.append(f"=== SAYFA {sh.name} {sh.nrows}x{sh.ncols}")
                for r in range(min(sh.nrows, 400)):
                    out.append(" | ".join(str(sh.cell_value(r, c)) for c in range(min(sh.ncols, 40))))
        else:
            wb = openpyxl.load_workbook(io.BytesIO(b), data_only=True, read_only=True)
            for ws in wb.worksheets:
                out.append(f"=== SAYFA {ws.title}")
                for i, r in enumerate(ws.iter_rows(values_only=True)):
                    if i > 400: break
                    out.append(" | ".join("" if x is None else str(x) for x in r[:40]))
    except Exception as e:
        out.append(f"HATA {e}")
    kaydet("x_" + desen.strip("-_") + ".txt", "\n".join(out))
    time.sleep(1)
