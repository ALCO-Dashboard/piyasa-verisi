import requests, time, zipfile, io, os
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"
D = "20261119"; Y, M = D[:4], D[4:6]
L = [f"/data/ttb/{Y}/{M}/ttb{D}3.zip", f"/data/ttb/{Y}/{M}/ttb{D}2.zip", f"/data/bappiyasaozet/piyasaozet_{D}.zip", f"/data/bapbultenozet/bultenozet_{D}.zip",
     f"/data/baprepovadeler/repovadeler_{D}.zip", f"/data/kmpbltn/{Y}/{M}/KMP{D}.zip", f"/data/tfd/{Y}/{M}/tfd{D}.zip", "/datum/tbliste.zip", f"/data/ttb/2025/01/ttb202501023.zip"]
for base in ["https://www.borsaistanbul.com", "https://borsaistanbul.com"]:
    for p in L:
        try:
            r = s.get(base + p, timeout=60); print(r.status_code, len(r.content), r.headers.get("content-type"), base + p)
            if r.status_code == 200 and r.content[:2] == b"PK":
                z = zipfile.ZipFile(io.BytesIO(r.content)); print("   ", [(n, z.getinfo(n).file_size) for n in z.namelist()])
                d = "out/" + os.path.basename(p)[:-4]; os.makedirs(d, exist_ok=True); z.extractall(d)
        except Exception as e: print("ERR", p, e)
        time.sleep(1.5)
    if os.listdir("out") and any(f for f in os.listdir("out") if f != "log.txt"): break
