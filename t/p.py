import requests, time, zipfile, io, os, re
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"
def get(u, ad=None):
    try:
        r = s.get(u, timeout=60); print(r.status_code, len(r.content), r.headers.get("content-type"), u)
        if ad: open("out/" + ad, "wb").write(r.content)
        time.sleep(1.5); return r
    except Exception as e: print("ERR", u, e)
get("https://borsaistanbul.com/files/DataFilePaths.zip", "DataFilePaths.zip")
get("https://borsaistanbul.com/files/borsa-istanbul-bap-veri-bildirim-ve-kabul-formatlari.pdf", "bap_format.pdf")
for u, a in [("https://borsaistanbul.com/veriler/borclanma-araclari-piyasasi-verileri/bulten-verileri", "bap_bulten.html"),
             ("https://borsaistanbul.com/veriler/borclanma-araclari-piyasasi-verileri", "bap.html"),
             ("https://borsaistanbul.com/veriler/borclanma-araclari-piyasasi-verileri/piyasa-verileri", "bap_piyasa.html"),
             ("https://borsaistanbul.com/veriler/kiymetli-madenler-ve-kiymetli-taslar-piyasasi", "kmtp.html")]:
    get(u, a)
try:
    z = zipfile.ZipFile("out/DataFilePaths.zip"); print(z.namelist())
    for n in z.namelist():
        b = z.read(n); open("out/dfp_" + os.path.basename(n), "wb").write(b)
except Exception as e: print("zip", e)
