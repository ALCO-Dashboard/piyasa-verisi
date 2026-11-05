"""Bloomberg köprüsü — Terminal'in açık olduğu bilgisayarda çalışır.

Ne yapar
  1) Bloomberg Desktop API (blpapi) ile Terminal'e bağlanır, SERILER listesindeki ticker'ların günlük PX_LAST
     geçmişini çeker (ilk çalıştırmada 2023'ten, sonra son 15 günü yeniler).
  2) Veriyi bu klasördeki bbg_onbellek.json'da biriktirir.
  3) Tamamını şifreleyip (AES-GCM, anahtar BBG_ANAHTAR) GitHub'daki bloomberg-veri dalına bbg.enc.json olarak yükler.
     Repo herkese açık olduğu için ham veri hiçbir zaman şifresiz gönderilmez.
  4) Siteyi güncelleyen iş akışını (sayfalar.yml) başlatır.

Kurulum (bir kez)
  py -m pip install --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/ blpapi
  py -m pip install cryptography
  Bu klasörde kopru_ayar.json oluşturun (kopru_ayar.ornek.json'u kopyalayıp doldurun).

Kullanım
  py kopru.py --test           Terminal'den çeker, son değerleri yazar, GitHub'a göndermez
  py kopru.py                 çeker ve gönderir (Görev Zamanlayıcı bunu çalıştırır)
"""
import argparse
import base64
import datetime as dt
import gzip
import json
import os
import sys
import urllib.error
import urllib.request

KOK = os.path.dirname(os.path.abspath(__file__))
AYAR = os.path.join(KOK, "kopru_ayar.json")
ONBELLEK = os.path.join(KOK, "bbg_onbellek.json")
GUNLUK = os.path.join(KOK, "kopru.log")
REPO = "ALCO-Dashboard/piyasa-verisi"
DAL = "bloomberg-veri"
DOSYA = "bbg.enc.json"
BAS = dt.date(2023, 1, 2)
YENILE_GUN = 15
ITER = 250000

# ticker -> kısa ad
SERILER = {
    "GOLDLNAM Index": "lbma_am",
    "GOLDLNPM Index": "lbma_pm",
    "TRYION Curncy": "try_imp_on",
    "TRYITN Curncy": "try_imp_tn",
    "TRYI1W Curncy": "try_imp_1h",
    "TRYI2W Curncy": "try_imp_2h",
    "TRYI1M Curncy": "try_imp_1a",
    "TRYI2M Curncy": "try_imp_2a",
    "TRYI3M Curncy": "try_imp_3a",
    "TRYI6M Curncy": "try_imp_6a",
    "TRYI9M Curncy": "try_imp_9a",
    "TRYI12M Curncy": "try_imp_1y",
    "TRYI2Y Curncy": "try_imp_2y",
}


def log(*a):
    satir = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} " + " ".join(str(x) for x in a)
    print(satir, flush=True)
    try:
        with open(GUNLUK, "a", encoding="utf-8") as f:
            f.write(satir + "\n")
    except OSError:
        pass


def bloomberg_cek(baslangic, bitis):
    import blpapi
    opt = blpapi.SessionOptions()
    opt.setServerHost("localhost")
    opt.setServerPort(8194)
    s = blpapi.Session(opt)
    if not s.start():
        raise RuntimeError("Terminal'e bağlanılamadı — Bloomberg Terminal açık ve oturum girilmiş olmalı")
    try:
        if not s.openService("//blp/refdata"):
            raise RuntimeError("//blp/refdata servisi açılamadı")
        svc = s.getService("//blp/refdata")
        req = svc.createRequest("HistoricalDataRequest")
        for t in SERILER:
            req.getElement("securities").appendValue(t)
        req.getElement("fields").appendValue("PX_LAST")
        req.set("startDate", baslangic.strftime("%Y%m%d"))
        req.set("endDate", bitis.strftime("%Y%m%d"))
        req.set("periodicitySelection", "DAILY")
        s.sendRequest(req)
        out, hata = {}, []
        while True:
            ev = s.nextEvent(30000)
            if ev.eventType() == blpapi.Event.TIMEOUT:
                raise RuntimeError("Bloomberg yanıt vermedi (30 sn)")
            for msg in ev:
                if msg.hasElement("responseError"):
                    raise RuntimeError(f"Bloomberg hatası: {msg.getElement('responseError')}")
                if not msg.hasElement("securityData"):
                    continue
                sd = msg.getElement("securityData")
                sec = sd.getElementAsString("security")
                if sd.hasElement("securityError"):
                    hata.append(sec)
                    continue
                fd = sd.getElement("fieldData")
                seri = out.setdefault(SERILER.get(sec, sec), {})
                for i in range(fd.numValues()):
                    row = fd.getValueAsElement(i)
                    if row.hasElement("PX_LAST"):
                        d = row.getElementAsDatetime("date")
                        seri[f"{d.year:04d}-{d.month:02d}-{d.day:02d}"] = round(row.getElementAsFloat("PX_LAST"), 6)
            if ev.eventType() == blpapi.Event.RESPONSE:
                break
        if hata:
            log("UYARI: Bloomberg bu ticker'ları tanımadı:", ", ".join(hata))
        return out
    finally:
        s.stop()


def sifrele(nesne, anahtar):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    ham = gzip.compress(json.dumps(nesne, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    tuz, iv = os.urandom(16), os.urandom(12)
    k = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=tuz, iterations=ITER).derive(anahtar.encode("utf-8"))
    b = lambda x: base64.b64encode(x).decode("ascii")
    return {"v": 1, "iter": ITER, "salt": b(tuz), "iv": b(iv), "ct": b(AESGCM(k).encrypt(iv, ham, None))}


def github(yontem, yol, token, govde=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{yol}", method=yontem,
                                 data=json.dumps(govde).encode() if govde is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "alco-bloomberg-kopru"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 404 and yontem == "GET":
            return None
        raise RuntimeError(f"GitHub {yontem} {yol}: HTTP {e.code} {e.read()[:300].decode('utf-8', 'replace')}")


def gonder(paket, token):
    icerik = base64.b64encode(json.dumps(paket).encode("utf-8")).decode("ascii")
    mevcut = github("GET", f"contents/{DOSYA}?ref={DAL}", token)
    govde = {"message": f"Bloomberg verisi {paket['zaman']}", "content": icerik, "branch": DAL}
    if mevcut and mevcut.get("sha"):
        govde["sha"] = mevcut["sha"]
    github("PUT", f"contents/{DOSYA}", token, govde)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="GitHub'a göndermeden çek ve göster")
    ap.add_argument("--bastan", action="store_true", help="önbelleği yok sayıp 2023'ten yeniden çek")
    a = ap.parse_args()
    try:
        ayar = json.load(open(AYAR, encoding="utf-8")) if os.path.exists(AYAR) else {}
        if not a.test and (not ayar.get("github_token") or not ayar.get("bbg_anahtar")):
            raise RuntimeError(f"{AYAR} içinde github_token ve bbg_anahtar olmalı")
        veri = {} if a.bastan or not os.path.exists(ONBELLEK) else json.load(open(ONBELLEK, encoding="utf-8"))
        son = max((max(v) for v in veri.values() if v), default=None)
        bas = BAS if not son else dt.date.fromisoformat(son) - dt.timedelta(days=YENILE_GUN)
        bugun = dt.date.today()
        log(f"Bloomberg'den çekiliyor: {bas} – {bugun}, {len(SERILER)} ticker")
        yeni = bloomberg_cek(bas, bugun)
        for k, seri in yeni.items():
            veri.setdefault(k, {}).update(seri)
        json.dump(veri, open(ONBELLEK, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        for t, k in SERILER.items():
            s = veri.get(k) or {}
            d = max(s) if s else None
            log(f"   {t:<16} {len(s):>5} gün   son {d or '—'}  {s.get(d, '') if d else ''}")
        if a.test:
            log("Test tamam — GitHub'a gönderilmedi.")
            return 0
        paket = {"zaman": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "seriler": {k: SERILER_TERS.get(k, k) for k in veri}, **sifrele(veri, ayar["bbg_anahtar"])}
        gonder(paket, ayar["github_token"])
        log("Gönderildi.")
        try:      # siteyi hemen yenile (token'da Actions: Read and write izni varsa)
            github("POST", "actions/workflows/sayfalar.yml/dispatches", ayar["github_token"], {"ref": "main"})
            log("Site güncellemesi başlatıldı.")
        except Exception as e:
            log(f"Site güncellemesi başlatılamadı (bir sonraki planlı çalışmada yenilenir): {e}")
        return 0
    except Exception as e:
        log(f"HATA: {type(e).__name__}: {e}")
        return 1


SERILER_TERS = {v: k for k, v in SERILER.items()}

if __name__ == "__main__":
    sys.exit(main())
