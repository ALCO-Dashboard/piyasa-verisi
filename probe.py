import re, requests, io, os, time
import xlrd, openpyxl
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
s = requests.Session(); s.headers.update({"User-Agent": UA})
os.makedirs("out", exist_ok=True)
def kaydet(ad, t): open("out/" + ad, "w", encoding="utf-8").write(t)
kfi = s.get("https://www.hmb.gov.tr/portal/v2/pages?slug=kamu-finansmani-istatistikleri", timeout=90).text.replace("\\/", "/")
for desen, n in [("Ic_Borc_Stoku_DIBS_Listesi", 60), ("Altin-Tahvili-", 400), ("Altina-Dayali-Kira-Sertifikasi-", 400), ("Doviz-Cinsi-Sabit-Faizli-Kuponlu-Senetler-2003", 400), ("Doviz-Cinsi-Kira-Sertifikasi-", 400), ("Kira-Sertifikasi-15", 60)]:
    m = re.findall(r"https://ms\.hmb\.gov\.tr/uploads/[^\"'\s<>]*" + re.escape(desen) + r"[^\"'\s<>]*\.xlsx?", kfi)
    if not m: print("YOK", desen); continue
    u = m[0]; b = s.get(u, timeout=120).content; print("İNDİ", u, len(b))
    out = []
    try:
        if u.endswith(".xls"):
            wb = xlrd.open_workbook(file_contents=b)
            for sh in wb.sheets():
                out.append(f"=== SAYFA {sh.name} {sh.nrows}x{sh.ncols}")
                for r in range(min(sh.nrows, n)):
                    out.append(" | ".join(str(sh.cell_value(r, c)) for c in range(min(sh.ncols, 25))))
        else:
            wb = openpyxl.load_workbook(io.BytesIO(b), data_only=True, read_only=True)
            for ws in wb.worksheets:
                out.append(f"=== SAYFA {ws.title}")
                for i, r in enumerate(ws.iter_rows(values_only=True)):
                    if i > n: break
                    out.append(" | ".join("" if x is None else str(x) for x in r[:25]))
    except Exception as e:
        out.append(f"HATA {e}")
    kaydet("y_" + desen.strip("-_") + ".txt", "\n".join(out))
    time.sleep(1)
