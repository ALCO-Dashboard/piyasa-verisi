#!/usr/bin/env python3
"""Borsa İstanbul bülten verileri: Borçlanma Araçları Piyasası (BAP) ve Kıymetli Madenler Piyasası (KMP).

Kaynak dosyalar (borsaistanbul.com, günlük):
  /data/ttb/YYYY/AA/ttbYYYYAAGG3.zip                  BAP günlük bülten (kıymet/vade bazında AOF, getiri, hacim)
  /data/bappiyasaozet/piyasaozet_YYYYAAGG.zip         BAP günlük özet (pazar ve menkul kıymet türü bazında toplam hacim)
  /data/kmpbltn/YYYY/AA/KMPYYYYAAGG.zip               KMP günlük bülten (Excel)
  /datum/tbliste.zip                                  işlem gören borçlanma araçları (getiri türü, ihraççı) — sınıflama için

Çıktı (site/makro/data/):
  bist.json            günlük özetler (grafik ve kutular)
  bist_kiymet.json     ISIN → ihraççı / getiri türü önbelleği (her çalışmada tbliste ile güncellenir)
  bist/YYYY-MM-DD.json gün bazında işlem detayları (sayfadaki detay tablosu bunu yükler)

İstekler arasında bekleme var; her çalışmada en fazla --max-gun gün indirilir, eksikler sonraki çalışmalarda tamamlanır.
Kullanım: python bist/guncelle.py --site site [--bas 2025-01-01] [--max-gun 40]
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import time
import zipfile

import requests

BASE = "https://www.borsaistanbul.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
BEKLE = 1.2          # istekler arası saniye
TR = dt.timezone(dt.timedelta(hours=3))

# vade kovaları (gün): 1A 3A 6A 1Y 2Y 5Y 10Y — sınırlar komşu vadelerin geometrik ortası
VADE_SINIR = [52, 129, 258, 516, 1154, 2581]

PAZAR = [  # (bülten pazar adı başlangıcı, anahtar)
    ("BAP KES NORMAL", "kes"), ("BAP KES KUCUK", "kes"),
    ("BAP REPO-T. REPO NORMAL", "repo"), ("BAP REPO-T. REPO KUCUK", "repos"),
    ("BAP BANKALARARASI REPO", "brep"), ("BAP MK TERCIHLI REPO", "mktr"), ("BAP PAY REPO", "prep"),
    ("BAP TAAHHUTLU", "ctm"), ("BAP PARA PIYASASI", "para"), ("BAP PARA SWAP", "fxsw"),
    ("BAP KIYMETLI MADEN", "kmsw"), ("BAP NY IHRAC", "ihrac"), ("BAP ULUSLARARASI EUROBOND", "eurob"),
    ("BAP GOZALTI", "gozalti"), ("BAP TEMERRUT", "temerrut"),
]


def log(*a):
    print(*a, flush=True)


def pazar(ad):
    ad = (ad or "").strip().upper()
    for p, k in PAZAR:
        if ad.startswith(p):
            return k
    return "diger"


def sayi(x):
    x = (x or "").strip()
    if not x or x == "-":
        return None
    try:
        return float(x.replace(",", "")) if x.count(".") <= 1 else float(x.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def vade_kova(gun):
    if gun is None:
        return None
    for i, s in enumerate(VADE_SINIR):
        if gun <= s:
            return i
    return len(VADE_SINIR)


def segment(isin):
    """Hazine DİBS / Hazine kira sertifikası / özel sektör kira sertifikası / özel sektör bono-tahvil."""
    i = (isin or "").upper()
    if i.startswith(("TRT", "TRB")):
        return "hdibs"
    if i.startswith("TRD"):
        return "hsukuk" if len(i) > 3 and i[3].isdigit() else "osukuk"
    if i.startswith("TR"):
        return "ozel"
    return "yabanci"


def getiri_turu(metin):
    m = (metin or "").upper()
    if "TÜFE" in m or "TUFE" in m or "CPI" in m:
        return "tufe"
    if "TLREF" in m:
        return "tlref"
    if m.startswith(("DEĞİŞKEN", "DEGISKEN", "GEÇMİŞ", "GECMIS")) or "VARIABLE" in m:
        return "degisken"
    if m.startswith(("SABİT", "SABIT", "İSKONTO", "ISKONTO")):
        return "sabit"
    return None


# ------------------------------------------------------------------ indirme
class Kaynak:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})
        self.n = 0

    def zip(self, yol):
        """zip dosyasını indirir; yoksa (404 / HTML) None."""
        if self.n:
            time.sleep(BEKLE)
        self.n += 1
        for deneme in range(3):
            try:
                r = self.s.get(BASE + yol, timeout=90)
                if r.status_code == 404 or not r.content.startswith(b"PK"):
                    return None
                r.raise_for_status()
                return zipfile.ZipFile(io.BytesIO(r.content))
            except (requests.RequestException, zipfile.BadZipFile) as e:
                if deneme == 2:
                    raise
                log(f"   tekrar ({type(e).__name__}): {yol}")
                time.sleep(5 * (deneme + 1))


def csv_oku(z):
    ad = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    b = z.read(ad)
    for kod in ("cp1254", "utf-8-sig", "latin-1"):
        try:
            t = b.decode(kod)
            break
        except UnicodeDecodeError:
            continue
    R = list(csv.reader(io.StringIO(t), delimiter=";"))
    if len(R) < 2:
        return [], []
    bas = [h.strip().upper() for h in R[0]]
    veri = [r for r in R[1:] if r and r[0].strip() and not r[0].strip().upper().startswith(("MARKET NAME", "PAZAR"))]
    return bas, veri


# ------------------------------------------------------------------ kıymet sınıflaması (tbliste)
def kiymet_guncelle(K, kay):
    z = kay.zip("/datum/tbliste.zip")
    if not z:
        log("   tbliste indirilemedi")
        return 0
    ad = next(n for n in z.namelist() if n.lower().endswith((".xls", ".xlsx")))
    b = z.read(ad)
    satirlar = []
    try:
        import xlrd
        wb = xlrd.open_workbook(file_contents=b)
        sh = wb.sheet_by_index(0)
        satirlar = [sh.row_values(i) for i in range(sh.nrows)]
    except Exception as e:
        try:
            import pandas as pd
            df = pd.read_excel(io.BytesIO(b), sheet_name=0, header=None)
            satirlar = df.where(df.notna(), None).values.tolist()
        except Exception as e2:
            log(f"   tbliste okunamadı: {e} / {e2}")
            return 0
    bi = next((i for i, r in enumerate(satirlar) if any(str(c or "").startswith("ISIN Kodu") for c in r)), None)
    if bi is None:
        return 0
    bas = [str(c or "").split("\n")[0].strip() for c in satirlar[bi]]
    ix = {h: j for j, h in enumerate(bas)}
    n = 0
    for r in satirlar[bi + 1:]:
        isin = str(r[ix["ISIN Kodu"]] or "").strip()
        if not re.match(r"^[A-Z]{2}[A-Z0-9]{10}$", isin):
            continue
        g = lambda k: str(r[ix[k]] or "").strip() if k in ix else ""
        tur = getiri_turu(g("Getiri Türü"))
        K[isin] = {"t": tur, "i": "H" if "Hazine" in g("İhraçcı Kurum") else "O", "mk": g("MK Türü").split(" / ")[0],
                   "ih": g("İhraçcı Kurum").split(" / ")[0][:60], "v": g("İtfa Tarihi")[:10], "g": g("Getiri Türü").split(" / ")[0]}
        n += 1
    return n


def tur_bul(K, isin, bilesik):
    k = K.get(isin)
    if k and k.get("t"):
        return k["t"]
    if isin.startswith("TRB"):
        return "sabit"                    # Hazine bonosu: iskontolu
    if isin.startswith(("TRT", "TRD")) and bilesik is not None and bilesik < 15:
        return "tufe"                     # listede olmayan (vadesi geçmiş) kıymet: reel getiri düzeyinden TÜFE'ye endeksli kabul
    return "bil"


# ------------------------------------------------------------------ günlük dosyalar
def ttb_isle(bas, veri, K):
    ix = {h: j for j, h in enumerate(bas)}

    def f(r, ad):
        j = ix.get(ad)
        return sayi(r[j]) if j is not None and j < len(r) else None

    def s(r, ad):
        j = ix.get(ad)
        return r[j].strip() if j is not None and j < len(r) else ""

    detay, kes, kf, M, sw, kmsw = [], {}, {}, {}, {}, []
    for r in veri:
        pz = pazar(s(r, "PAZAR ISMI"))
        isin, para = s(r, "ISIN/KOD"), s(r, "PARA BIRIMI")
        gun = f(r, "VKG/REPO SURESI")
        aof, getiri, bil = f(r, "AG.ORT. FIYAT/ORAN/SWAP PUANI"), f(r, "AG. ORT.FIYAT/GETIRI"), f(r, "AG. ORT. BILESIK GETIRI")
        hac = f(r, "TOPLAM ISLEM HACMI") or f(r, "ISLEM HACMI") or 0
        hac_n = f(r, "ISLEM HACMI") or 0          # oranı olan (normal) işlemler
        adet = f(r, "TOPLAM ISLEM SAYISI") or f(r, "ISLEM SAYISI") or 0
        nom = f(r, "TOPLAM MIKTAR") or f(r, "MIKTAR")
        seg = tur = ""
        if pz == "kes":
            seg = segment(isin)
            tur = tur_bul(K, isin, bil)
            if para == "TRY" and seg != "yabanci":
                c = kes.setdefault((seg, tur, vade_kova(gun)), [0, 0, 0, 0, 0])
                c[0] += hac
                if bil is not None and hac_n > 0:          # getiri yalnızca sabit/TÜFE'li kıymetlerde var
                    c[1] += bil * hac_n
                    c[2] += hac_n
                if aof is not None and hac_n > 0:          # endeksli / kira sertifikalarında ağırlıklı ortalama fiyat
                    c[3] += aof * hac_n
                    c[4] += hac_n
            else:
                kf[para] = kf.get(para, 0) + hac
        elif pz == "fxsw":
            cift = isin.replace("_SWAP", "")
            if gun and aof is not None and getiri:
                sw.setdefault(cift, []).append([int(gun), aof, getiri, round(hac / 1e6, 2), round((nom or 0) / 1e6, 2)])
        elif pz == "kmsw":
            kmsw.append([int(gun or 0), aof, getiri, round(hac / 1e6, 2)])
        if pz not in ("kes", "fxsw"):
            m = M.setdefault(pz, {"h": 0, "n": 0, "rw": 0, "rh": 0, "on": [0, 0]})
            if para in ("TRY", ""):
                m["h"] += hac
            m["n"] += adet
            if aof is not None and hac_n > 0 and pz in ("repo", "repos", "brep", "ctm", "para", "mktr", "prep"):
                m["rw"] += aof * hac_n
                m["rh"] += hac_n
                if gun is not None and gun <= 4:
                    m["on"][0] += aof * hac_n
                    m["on"][1] += hac_n
        detay.append([pz, s(r, "ISLEM KODU"), isin, s(r, "VALOR1"), s(r, "VALOR2"), para, int(gun) if gun is not None else None,
                      aof, f(r, "KAPANIS"), getiri, bil, round(hac, 2), nom, int(adet), seg, tur])
    gunluk = {
        "k": [[s_, t_, v_, round(c[0] / 1e6, 3), round(c[1] / 1e6, 4), round(c[2] / 1e6, 3), round(c[3] / 1e6, 4), round(c[4] / 1e6, 3)] for (s_, t_, v_), c in sorted(kes.items(), key=lambda x: (x[0][0], x[0][1], x[0][2] if x[0][2] is not None else -1))],
        "kf": {k: round(v / 1e6, 3) for k, v in kf.items()},
        "m": {k: {"h": round(m["h"] / 1e6, 2), "n": int(m["n"]), "r": round(m["rw"] / m["rh"], 4) if m["rh"] else None,
                  "ron": round(m["on"][0] / m["on"][1], 4) if m["on"][1] else None} for k, m in M.items()},
        "sw": sw,
    }
    if kmsw:
        gunluk["kmsw"] = kmsw
    return gunluk, detay


def ozet_isle(veri):
    pz, gor = {}, set()
    turlu = {(pazar(r[0]), r[3].strip()) for r in veri if len(r) >= 7 and r[1].strip()}
    for r in veri:
        if len(r) < 7:
            continue
        k, tip, mk, para = pazar(r[0]), r[1].strip(), r[2].strip(), r[3].strip()
        h = sayi(r[5])
        if h is None:
            continue
        if tip:
            if tip != mk:
                continue
        else:
            if (k, para) in turlu:
                continue
            t = tuple(x.strip() for x in r)
            if t in gor:
                continue
            gor.add(t)
        pz.setdefault(k, {})
        pz[k][para] = round(pz[k].get(para, 0) + h / 1e6, 2)
    return pz


def kmp_isle(z):
    import openpyxl
    ad = next((n for n in z.namelist() if n.lower().endswith(".xlsx")), None)
    if not ad:
        return None, []
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(io.BytesIO(z.read(ad)), data_only=True, read_only=True)
    sh = {ws.title.strip().lower(): ws for ws in wb.worksheets}
    MET = {"ALTIN": "au", "GÜMÜŞ": "ag", "PLATİN": "pt", "PALADYUM": "pd"}
    km = {}
    gs = next((ws for k, ws in sh.items() if k.startswith("genel")), None)
    if gs is not None:
        for r in gs.iter_rows(values_only=True):
            c = [x for x in r if x is not None]
            if not c or not isinstance(c[0], str):
                continue
            m = re.match(r"^\s*(ALTIN|GÜMÜŞ|PLATİN|PALADYUM)\s+TOPLAMI\s*$", c[0].upper())
            nums = [x for x in c[1:] if isinstance(x, (int, float))]
            if m:
                k = MET[m.group(1)]
                d = km.setdefault(k, {})
                if len(nums) == 2:
                    d["kg"], d["n"] = round(nums[0], 3), int(nums[1])
                elif len(nums) >= 6:
                    d["h"], d["hu"] = round(nums[3] / 1e6, 3), round(nums[4] / 1e6, 4)
    fs = next((ws for k, ws in sh.items() if k.startswith("fiyat")), None)
    if fs is not None:
        bas = None
        for r in fs.iter_rows(values_only=True):
            c = list(r)
            t = next((x for x in c if x is not None), None)
            if not isinstance(t, str):
                continue
            t = t.strip()
            ilk = next((x for x in c if isinstance(x, (int, float))), None)
            if t.startswith("Referans Fiyat ve Metal"):
                bas = [str(x or "").strip() for x in c]
                continue
            if bas and t.startswith("Metal Fiyati"):
                birim = "aof" if "TRY/KG" in t else "aofu" if "USD/ONS" in t else None
                if birim:
                    for j, ad_ in enumerate(bas):
                        k = {"Altın": "au", "Gümüş": "ag", "Platin": "pt", "Paladyum": "pd"}.get(ad_)
                        if k and j < len(c) and isinstance(c[j], (int, float)):
                            km.setdefault(k, {})[birim] = round(c[j], 2)
            elif t.startswith("AOF (USD/ONS)") and "Fiksing" not in t and ilk is not None:
                km.setdefault("au", {})["aofu"] = round(ilk, 2)
            elif t.startswith("AOF (TRY/KG)") and ilk is not None:
                km.setdefault("au", {})["aof"] = round(ilk, 2)
            elif t.startswith("USD/TRY") and ilk is not None:
                km["usd"] = ilk
    seri = []
    ss = next((ws for k, ws in sh.items() if k.startswith("seri")), None)
    if ss is not None:
        bas = None
        for r in ss.iter_rows(values_only=True):
            c = list(r)
            if c and c[0] == "Seriler":
                bas = [str(x or "").strip() for x in c]
                continue
            if bas and c and isinstance(c[0], str) and c[0].strip():
                d = dict(zip(bas, c))
                seri.append([d.get("Seriler"), d.get("Kıymetli Maden"), d.get("Market Segment"), d.get("Fiyat Birimi"), d.get("Ayar"),
                             d.get("Takas Tarihi"), d.get("Adet"), d.get("TL İşlem Hacmi"), d.get("USD İşlem Hacmi"), d.get("İşlem Sayısı"),
                             d.get("AOF"), d.get("En Düşük Fiyat"), d.get("En Yüksek Fiyat"), d.get("Kapanış Fiyatı")])
    return km, seri


# ------------------------------------------------------------------ ana akış
def is_gunleri(bas, bit):
    d = bas
    while d <= bit:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site")
    ap.add_argument("--bas", default="2025-01-01")
    ap.add_argument("--max-gun", type=int, default=40)
    ap.add_argument("--sure", type=int, default=0, help="en fazla bu kadar dakika çalış (0: sınırsız)")
    a = ap.parse_args()
    t0 = time.time()
    kok = os.path.join(a.site, "makro", "data")
    os.makedirs(os.path.join(kok, "bist"), exist_ok=True)
    yol, kyol = os.path.join(kok, "bist.json"), os.path.join(kok, "bist_kiymet.json")
    try:
        D = json.load(open(yol, encoding="utf-8"))
    except Exception:
        D = {}
    try:
        K = json.load(open(kyol, encoding="utf-8"))
    except Exception:
        K = {}
    G, KM, YOK = D.setdefault("g", {}), D.setdefault("km", {}), set(D.get("yok", []))
    kay = Kaynak()
    try:
        n = kiymet_guncelle(K, kay)
        log(f"tbliste: {n} kıymet, önbellekte {len(K)}")
    except Exception as e:
        log(f"HATA tbliste: {type(e).__name__}: {e}")
    simdi = dt.datetime.now(TR)
    bugun = simdi.date()
    # bugünün bülteni akşam yayımlanır; 18:30'dan önce bugünü deneme
    son = bugun if simdi.hour * 60 + simdi.minute >= 18 * 60 + 30 else bugun - dt.timedelta(days=1)
    eksik = [d for d in is_gunleri(dt.date.fromisoformat(a.bas), son)
             if d.isoformat() not in YOK and (d.isoformat() not in G or d.isoformat() not in KM)]
    eksik.sort(reverse=True)        # önce en yeni günler
    log(f"eksik iş günü: {len(eksik)} (bu çalışmada en fazla {a.max_gun})")
    islenen, hatalar = 0, []
    for d in eksik[:a.max_gun]:
        if a.sure and time.time() - t0 > a.sure * 60:
            log("süre doldu")
            break
        iso, ymd = d.isoformat(), d.strftime("%Y%m%d")
        Y, A = ymd[:4], ymd[4:6]
        try:
            detay = {}
            if iso not in G:
                z = kay.zip(f"/data/ttb/{Y}/{A}/ttb{ymd}3.zip")
                if z is None:
                    if (bugun - d).days >= 3:
                        YOK.add(iso)          # tatil / işlem yok
                        log(f"{iso}: bülten yok (tatil)")
                    continue
                bas, veri = csv_oku(z)
                g, det = ttb_isle(bas, veri, K)
                zo = kay.zip(f"/data/bappiyasaozet/piyasaozet_{ymd}.zip")
                if zo:
                    _, vo = csv_oku(zo)
                    g["pz"] = ozet_isle(vo)
                G[iso] = g
                detay["bap"] = det
            if iso not in KM:
                zk = kay.zip(f"/data/kmpbltn/{Y}/{A}/KMP{ymd}.zip")
                if zk is not None:
                    km, seri = kmp_isle(zk)
                    if km:
                        KM[iso] = km
                        detay["kmp"] = seri
                elif (bugun - d).days >= 3:
                    KM[iso] = {}
            if detay:
                dy = os.path.join(kok, "bist", iso + ".json")
                try:
                    eski = json.load(open(dy, encoding="utf-8"))
                except Exception:
                    eski = {}
                eski.update(detay)
                json.dump(eski, open(dy, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            islenen += 1
            g = G.get(iso, {})
            log(f"{iso}: KES {sum(c[3] for c in g.get('k', [])):,.0f} mn TL · repo {g.get('m', {}).get('repo', {}).get('h', 0):,.0f} mn · "
                f"swap {sum(len(v) for v in g.get('sw', {}).values())} vade · KMP altın {KM.get(iso, {}).get('au', {}).get('h', '—')} mn TL")
        except Exception as e:
            log(f"HATA {iso}: {type(e).__name__}: {e}")
            hatalar.append(iso)
    D["yok"] = sorted(YOK)
    D["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    D["vade_sinir"] = VADE_SINIR
    D["eksik"] = max(0, len(eksik) - islenen)
    json.dump(D, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(K, open(kyol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    log(f"yazıldı: {yol} ({os.path.getsize(yol) // 1024} KB, {len(G)} gün BAP, {len(KM)} gün KMP) · bu çalışmada {islenen} gün · kalan {D['eksik']}")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ortak"))
        from durum import yaz
        if G:
            yaz(a.site, "bist", max(G))
    except Exception as e:
        log(f"durum.json yazılamadı: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
