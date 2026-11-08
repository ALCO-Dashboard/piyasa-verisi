"""Bankacılık Verileri → TCMB → Zorunlu Karşılık.

Kaynaklar
  TCMB Zorunlu Karşılıklar sayfası (www.tcmb.gov.tr … /bankacilik+verileri/zorunlu+karsiliklar):
    - "TL cinsinden tesis edilmesi gereken ortalama zorunlu karşılık tutarı" PDF'i (her tesis dönemi değişir;
      hesaplama tarihi, tesis dönemi ilk günü, ortalama ve bloke tutar, milyar TL, geçici)
    - TRZK verileri.xlsx: geçmiş tesis dönemleri (TL/YP tesis edilmesi gereken ve tesis edilen, ağırlıklı ortalama ZK oranı)
    - zko.pdf: zorunlu karşılık oranları (TL, YP)
    - TL ve YP zorunlu karşılıklara uygulanan faiz/nema oranları PDF'leri
  TCMB Taraflı Döviz Depo sayfası: döviz depo vadeleri, faiz oranları ve limitleri PDF'i
  TCMB EVDS: bankalar serbest mevduatı (TP.PPIBSM), gün başı toplam likidite (TP.PPIGBTL), TCMB AOF (TP.APIFON4)

Anlık hesap (kullanıcının Excel'deki "TCMB ZK Anlık" mantığı)
  Tesis tutarı (G)        = PDF ortalama tutar + önceki dönemden devreden fark (önceki dönem arşivdeyse: gereken − tesis edilen)
  Ortalama tutulan (H)    = tesis döneminin geçen günlerindeki gün sonu serbest mevduat ortalaması. Bir takvim gününün gün sonu
                            bakiyesi, sonraki iş gününün EVDS gün başı serbest mevduat değeridir (hafta sonu/tatil cuma değerini taşır).
  Tutulması gereken (I)   = (G × 14 − H × geçen gün) / kalan gün   → kalan günlerde tutulması gereken ortalama
  Piyasa likidite durumu  = gün başı toplam likidite − I   (+ fazla, − eksik)
Geçmiş dönemlerde PDF yoksa ortalama tutar = arşivdeki toplam gereken − bloke (bloke ≈ TL tesis edilen − dönemin
ortalama serbest mevduatı) olarak tahmin edilir.

Çıktı: site/zk/index.html, site/zk/data/zk.json
Kullanım: python zk/guncelle.py --site site
"""
import argparse
import datetime as dt
import html as htmlmod
import importlib.util
import io
import json
import os
import re
import sys
import time

import requests

KOK = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TCMB = "https://www.tcmb.gov.tr"
ZK_SAYFA = TCMB + "/wps/wcm/connect/tr/tcmb+tr/main+menu/istatistikler/bankacilik+verileri/zorunlu+karsiliklar"
DEPO_SAYFA = TCMB + "/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Istatistikler/Piyasa+Verileri/doviz+depo+limit"
BAS = dt.date(2011, 9, 1)
GUN = 14

# Zorunlu karşılık oranları tablosunun güncel yapısındaki kalemler (değer sayısı tutarsa kullanılır)
TL_KALEM = ["Kur korumalı hesaplar (6 aya kadar)", "Kur korumalı hesaplar (1 yıl ve üzeri)", "Vadesiz, ihbarlı mevduat, özel cari hesaplar",
            "1 aya kadar vadeli mevduat/katılım fonu", "3 aya kadar vadeli mevduat/katılım fonu", "6 aya kadar vadeli mevduat/katılım fonu",
            "1 yıla kadar vadeli mevduat/katılım fonu", "1 yıl ve daha uzun vadeli mevduat/katılım fonu",
            "Diğer yük. (1 aya kadar): yurt dışı repo ve krediler", "Diğer yük. (3 aya kadar): yurt dışı repo ve krediler",
            "Diğer yük. (1 yıla kadar): yurt dışı kaynaklı / merkez", "Diğer yük. (1 yıla kadar): diğer",
            "Diğer yük. (3 yıla kadar)", "Diğer yük. (3 yıldan uzun)"]
YP_KALEM = ["Vadesiz, ihbarlı ve 1 aya kadar vadeli mevduat/katılım fonu (kıymetli maden dahil)",
            "3 ay, 6 ay, 1 yıla kadar ve daha uzun vadeli mevduat/katılım fonu (kıymetli maden dahil)",
            "Diğer yük. (1 yıla kadar): yurt içi yerleşiklerle repo", "Diğer yük. (1 yıla kadar): diğer",
            "Diğer yük. (2 yıla kadar)", "Diğer yük. (3 yıla kadar)", "Diğer yük. (5 yıla kadar)", "Diğer yük. (5 yıldan uzun)"]
YP_NEMA = ["USD zorunlu karşılıklara faiz/nema (%)", "EUR hesaplara komisyon (%)", "USD mevduat ZK'sına komisyon (%)",
           "USD dışı döviz mevduat ZK'sına komisyon (%)", "YP mevduat için tesis edilmesi gereken ZK'ya komisyon (%)"]
DEPO_KOL = ["alis_2g_usd", "alis_2g_eur", "alis_1h_usd", "alis_1h_eur", "alis_2h_usd", "alis_2h_eur", "alis_1a_usd", "alis_1a_eur",
            "limit_usd", "limit_eur", "satis_1h_usd", "satis_1h_eur", "satis_1a_usd", "satis_1a_eur"]


def log(*a):
    print(*a, flush=True)


def tarih(s):
    m = re.match(r"^\s*(\d{1,2})[./](\d{1,2})[./](\d{4})", str(s or ""))
    return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def trsayi(s):
    s = re.sub(r"\(\d+\)", "", str(s)).strip()
    try:
        return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)
    except ValueError:
        return None


# ------------------------------------------------------------------ indirme
def oturum():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})
    return s


def getir(s, url, ikili=True):
    for deneme in range(3):
        try:
            r = s.get(url, timeout=90)
            r.raise_for_status()
            return r.content if ikili else r.text
        except Exception:
            if deneme == 2:
                raise
            time.sleep(4)


def baglantilar(s):
    out = {}
    h = getir(s, ZK_SAYFA, False)
    hrefs = [htmlmod.unescape(m.group(1)) for m in re.finditer(r'href="([^"]+)"', h)]
    hrefs = [TCMB + x if x.startswith("/") else x for x in hrefs]
    ilk = lambda desen: next((x for x in hrefs if re.search(desen, x, re.I)), None)
    out["tesis"] = ilk(r"tesis(\+|%20| )edilmesi(\+|%20| )gereken.*\.pdf")
    out["arsiv"] = ilk(r"TRZK(\+|%20| )verileri\.xlsx")
    out["oran"] = ilk(r"/zko\.pdf")
    out["nema_tl"] = ilk(r"TL-uygulanan")                # ilk bağlantı en güncel dönem (01.06.2018 sonrası)
    out["nema_yp"] = ilk(r"YP-uygulanan")
    try:
        h2 = getir(s, DEPO_SAYFA, False)
        d = [htmlmod.unescape(m.group(1)) for m in re.finditer(r'href="([^"]+\.pdf[^"]*)"', h2)]
        d = [TCMB + x if x.startswith("/") else x for x in d]
        out["depo"] = next((x for x in d if re.search(r"Vadeleri", x)), None) or next((x for x in d if re.search(r"Depo", x)), None)
    except Exception as e:
        log(f"HATA döviz depo sayfası: {type(e).__name__}: {e}")
    return {k: v for k, v in out.items() if v}


# ------------------------------------------------------------------ ayrıştırıcılar
def pdf_metin(icerik):
    import pypdf
    return "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(icerik)).pages)


def tesis_pdf(icerik):
    t = pdf_metin(icerik)
    m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s+(\d{2}\.\d{2}\.\d{4})\s+([\d.]+,\d+)\s+([\d.]+,\d+)", t)
    if not m:
        raise ValueError("tesis PDF'inde tarih/tutar satırı bulunamadı")
    bas = tarih(m.group(2))
    return {"hesap": tarih(m.group(1)).isoformat(), "bas": bas.isoformat(), "bit": (bas + dt.timedelta(days=GUN - 1)).isoformat(),
            "ort": trsayi(m.group(3)), "bloke": trsayi(m.group(4))}       # milyar TL


def arsiv_xlsx(icerik):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(icerik), data_only=True, read_only=True)
    ad = {ws.title.strip(): ws for ws in wb.worksheets}

    def satirlar(ws):
        for r in ws.iter_rows(values_only=True):
            if r and isinstance(r[0], (dt.datetime, dt.date)) and isinstance(r[1], (dt.datetime, dt.date)):
                yield [x.date() if isinstance(x, dt.datetime) else x for x in r]
    out = {"tl": [], "yp": [], "oran": []}
    ws = next((w for k, w in ad.items() if k.startswith("TLZK Tesis")), None)
    for r in satirlar(ws) if ws else []:
        if isinstance(r[3], (int, float)):
            sy = lambda x: x if isinstance(x, (int, float)) else 0
            out["tl"].append({"yuk": r[0].isoformat(), "bas": r[1].isoformat(), "bit": r[2].isoformat(), "gereken": r[3], "edilen": r[4] if isinstance(r[4], (int, float)) else None,
                              "rom": sy(r[5]) + sy(r[6]) + (sy(r[7]) if len(r) > 7 else 0)})     # döviz + altın ile tesis (ROM), USD
    ws = next((w for k, w in ad.items() if k.startswith("YPZK Tesis")), None)
    for r in satirlar(ws) if ws else []:
        if isinstance(r[3], (int, float)):
            out["yp"].append({"bas": r[1].isoformat(), "gereken": r[3], "dvz": r[4], "altin": r[5]})
    ws = next((w for k, w in ad.items() if k.startswith("ZK Ağırlıklı")), None)
    for r in satirlar(ws) if ws else []:
        if isinstance(r[3], (int, float)):
            out["oran"].append({"bas": r[1].isoformat(), "tl": round(r[3], 3), "yp": round(r[4], 3) if isinstance(r[4], (int, float)) else None})
    return out


def oran_pdf(icerik):
    """zko.pdf → {tl: {...}, yp: {...}}: her bölümün son iki tebliğ satırı (değerler sütun konumuna göre sıralı)."""
    import pdfplumber
    bolum, satir = None, {"tl": [], "yp": []}
    with pdfplumber.open(io.BytesIO(icerik)) as pdf:
        for p in pdf.pages:
            W = p.extract_words(x_tolerance=1.5)
            metin = " ".join(w["text"] for w in W[:40])
            if "TÜRK" in metin and "LİRASI" in metin:
                bolum = "tl"
            elif "YABANCI" in metin:
                bolum = "yp"
            if not bolum:
                continue
            sol = p.width * .2
            teb = sorted([w for w in W if re.match(r"^\d{4}/\d+(\(\d+\))?$", w["text"]) and w["x0"] < sol], key=lambda w: w["top"])
            for q in teb:
                ayni = sorted([w for w in W if abs(w["top"] - q["top"]) < 3 and w["x0"] > q["x1"]], key=lambda w: w["x0"])
                deg, don = [], []
                for w in ayni:
                    if re.match(r"^\d{1,2}\.\d{2}\.\d{4}", w["text"]) or w["text"] == "-":
                        don.append(w["text"])
                    elif re.match(r"^\d+(,\d+)?$", w["text"]) and not don:
                        deg.append(trsayi(w["text"]))
                if deg and don:                       # dipnotlardaki tebliğ atıflarını ayıkla: satırda yürürlük tarihi olmalı
                    satir[bolum].append({"teblig": re.sub(r"\(\d+\)$", "", q["text"]), "donem": " ".join(don).replace(" - ", " – ").replace("-", " – ").strip(" –").strip(), "deger": deg})
    out = {}
    for k, kal in (("tl", TL_KALEM), ("yp", YP_KALEM)):
        S = satir[k]
        if not S:
            continue
        son, onc = S[-1], (S[-2] if len(S) > 1 else None)
        ad = kal if len(son["deger"]) == len(kal) else [f"Kalem {i + 1}" for i in range(len(son["deger"]))]
        if onc and len(onc["deger"]) == len(son["deger"]) + 1:     # bir önceki tabloda başta fazladan sütun (ör. kaldırılan kalem)
            onc = {**onc, "deger": onc["deger"][1:]}
        ayni = onc and len(onc["deger"]) == len(son["deger"])
        out[k] = {"teblig": son["teblig"], "donem": son["donem"], "onceki_teblig": onc["teblig"] if onc else None, "onceki_donem": onc["donem"] if onc else None,
                  "etiket_tahmini": len(son["deger"]) != len(kal),
                  "kalem": [{"ad": ad[i], "oran": v, "onceki": onc["deger"][i] if ayni else None} for i, v in enumerate(son["deger"])]}
    return out


def nema_tl(icerik):
    t = pdf_metin(icerik)
    out = []
    for m in re.finditer(r"^(\d{1,2}\.\d{2}\.\d{4})\s*-\s*(\d{1,2}\.\d{2}\.\d{4})?\s*(.+)$", t, re.M):
        kural = re.sub(r"\(\d+\)", "", m.group(3)).strip()
        carpan = re.search(r"\*\s*([\d,]+)", kural)
        baz = "aof" if re.search("fonlama maliyeti|funding cost", kural) else "politika" if re.search("Politika faizi|Policy rate", kural) else None
        if baz and carpan:
            kural = ("TCMB ağırlıklı ortalama fonlama maliyeti" if baz == "aof" else "Politika faizi") + f" × {carpan.group(1)}"
        out.append({"bas": tarih(m.group(1)).isoformat(), "bit": tarih(m.group(2)).isoformat() if m.group(2) else None, "kural": kural,
                    "baz": baz, "carpan": trsayi(carpan.group(1)) if carpan else None})
    return out


def nema_yp(icerik):
    t = pdf_metin(icerik)
    out = []
    for m in re.finditer(r"^(\d{1,2}\.\d{2}\.\d{4})\s*-\s*(\d{1,2}\.\d{2}\.\d{4})?\s+((?:[\d,]+\s*(?:\(\d+\))?\s*){5})$", t, re.M):
        deg = [trsayi(x) for x in re.findall(r"([\d,]+)(?:\s*\(\d+\))?", m.group(3))][:5]
        out.append({"bas": tarih(m.group(1)).isoformat(), "bit": tarih(m.group(2)).isoformat() if m.group(2) else None, "deger": deg})
    return out


def depo_pdf(icerik):
    t = pdf_metin(icerik)
    out = []
    for m in re.finditer(r"^(\d{1,2}\.\d{2}\.\d{4})((?:\s+\d+\.\d{2}){14})\s*$", t, re.M):
        out.append([tarih(m.group(1)).isoformat()] + [float(x) for x in m.group(2).split()])
    out.sort()
    return {"kolon": DEPO_KOL, "satir": out}


# ------------------------------------------------------------------ hesap
def evds_mod():
    sp = importlib.util.spec_from_file_location("tcmb_guncelle", os.path.join(os.path.dirname(KOK), "tcmb", "guncelle.py"))
    tm = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(tm)
    return tm.evds


def hesapla(seri, arsiv, pdfler):
    """seri: {tarih: {bsm, gbl}} (milyon TL) → günlük dizi ve dönem tablosu (milyar TL)."""
    gunler = sorted(d for d, v in seri.items() if v.get("bsm") is not None)
    if not gunler:
        return None
    gd = [dt.date.fromisoformat(d) for d in gunler]
    bsm = [seri[d]["bsm"] for d in gunler]
    import bisect

    def eod(k):            # takvim günü k'nın gün sonu serbest mevduatı = k'dan sonraki ilk iş günü gün başı değeri
        j = bisect.bisect_right(gd, k)
        return bsm[j] if j < len(gd) else None
    # dönemler: arşiv + PDF + aradaki boşluklar (14 günlük adım)
    D = {}
    for a in arsiv.get("tl", []):
        D[a["bas"]] = {"yuk": a["yuk"], "bas": a["bas"], "bit": a["bit"], "gereken_top": a["gereken"], "edilen_top": a["edilen"], "rom": a.get("rom", 0)}
    for b, p in pdfler.items():
        D.setdefault(b, {"bas": b, "bit": p["bit"]}).update({"ort_pdf": p["ort"] * 1e3, "bloke_pdf": p["bloke"] * 1e3, "hesap": p["hesap"]})
    if not D:
        return None
    son_gun = gd[-1]
    b = dt.date.fromisoformat(min(D))
    while b + dt.timedelta(days=GUN) <= son_gun:     # arşivde de PDF'te de olmayan dönemler (14 günlük adım)
        b += dt.timedelta(days=GUN)
        D.setdefault(b.isoformat(), {"bas": b.isoformat(), "bit": (b + dt.timedelta(days=GUN - 1)).isoformat()})
    donem = [D[k] for k in sorted(D)]
    for i, p in enumerate(donem):
        b0, b1 = dt.date.fromisoformat(p["bas"]), dt.date.fromisoformat(p["bit"])
        e = [eod(b0 + dt.timedelta(days=k)) for k in range(GUN)]
        p["tutulan"] = sum(e) / GUN if all(x is not None for x in e) and b1 < son_gun else None
        if p.get("ort_pdf") is not None:
            p["ort"], p["bloke"], p["kaynak"] = p["ort_pdf"], p["bloke_pdf"], "pdf"
        elif p.get("gereken_top") is not None and p.get("edilen_top") is not None and p["tutulan"] is not None and (p.get("rom") or 0) < 1:
            # ROM döneminde (döviz/altınla tesis) TL karşılığı bilinmediği için tahmin yapılmaz
            bloke = max(0.0, p["edilen_top"] - p["tutulan"])
            p["ort"], p["bloke"], p["kaynak"] = p["gereken_top"] - bloke, bloke, "tahmin"
        else:
            p["ort"], p["bloke"], p["kaynak"] = None, None, None
        onc = donem[i - 1] if i else None
        p["devir"] = (onc["gereken_top"] - onc["edilen_top"]) if onc and onc.get("gereken_top") is not None and onc.get("edilen_top") is not None \
            and (onc.get("rom") or 0) < 1 and dt.date.fromisoformat(onc["bit"]) == b0 - dt.timedelta(days=1) else 0.0
        p["tesis"] = p["ort"] + p["devir"] if p["ort"] is not None else None
        p["fark"] = p["tutulan"] - p["tesis"] if p["tutulan"] is not None and p["tesis"] is not None else None
    # günlük dizi
    bas_list = [dt.date.fromisoformat(p["bas"]) for p in donem]
    G = {k: [] for k in ("dates", "serbest", "gunbasi", "tesis", "ortalama", "gereken", "likidite", "donem")}
    for t, ts in zip(gd, gunler):
        j = bisect.bisect_right(bas_list, t) - 1
        if j < 0:
            continue
        p = donem[j]
        b0, b1 = bas_list[j], dt.date.fromisoformat(p["bit"])
        if t > b1:
            continue
        n = (t - b0).days
        e = [eod(b0 + dt.timedelta(days=k)) for k in range(n)]
        H = sum(e) / n if n and all(x is not None for x in e) else None
        Gt = p["tesis"]
        I = (Gt * GUN - (H or 0) * n) / (GUN - n) if Gt is not None and (H is not None or n == 0) and GUN - n > 0 else None
        J = seri[ts].get("gbl")
        r1 = lambda v: round(v / 1e3, 1) if v is not None else None          # milyon → milyar TL
        G["dates"].append(ts); G["serbest"].append(r1(seri[ts]["bsm"])); G["gunbasi"].append(r1(J)); G["tesis"].append(r1(Gt))
        G["ortalama"].append(r1(H)); G["gereken"].append(r1(I)); G["likidite"].append(r1(J - I) if J is not None and I is not None else None)
        G["donem"].append(j)
    r1 = lambda v: round(v / 1e3, 1) if v is not None else None
    dl = [{"yuk": p.get("yuk"), "hesap": p.get("hesap"), "bas": p["bas"], "bit": p["bit"], "ort": r1(p["ort"]), "bloke": r1(p["bloke"]), "devir": r1(p["devir"]),
           "tesis": r1(p["tesis"]), "tutulan": r1(p["tutulan"]), "fark": r1(p["fark"]), "gereken_top": r1(p.get("gereken_top")), "edilen_top": r1(p.get("edilen_top")),
           "kaynak": p["kaynak"]} for p in donem]
    return {"gunluk": G, "donemler": dl}


# ------------------------------------------------------------------ ana akış
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site")
    ap.add_argument("--yerel", help="test: TCMB dosyalarını bu klasörden oku (tesis.pdf, arsiv.xlsx, oran.pdf, nema_tl.pdf, nema_yp.pdf, depo.pdf)")
    ap.add_argument("--evds-json", help="test: EVDS serilerini bu JSON'dan oku ({tarih: {bsm, gbl, aof}})")
    a = ap.parse_args()
    cikti = os.path.join(a.site, "zk")
    os.makedirs(os.path.join(cikti, "data"), exist_ok=True)
    yol = os.path.join(cikti, "data", "zk.json")
    try:
        D = json.load(open(yol, encoding="utf-8"))
    except Exception:
        D = {}
    sorun = []
    # 1) TCMB dosyaları
    dosya = {}
    if a.yerel:
        for k in ("tesis", "arsiv", "oran", "nema_tl", "nema_yp", "depo"):
            f = next((os.path.join(a.yerel, x) for x in os.listdir(a.yerel) if x.split(".")[0] == k), None)
            if f:
                dosya[k] = open(f, "rb").read()
    else:
        s = oturum()
        try:
            L = baglantilar(s)
            log("bağlantılar: " + ", ".join(f"{k}={os.path.basename(v.split('?')[0])}" for k, v in L.items()))
            D["kaynak"] = {k: v for k, v in L.items()}
        except Exception as e:
            log(f"HATA TCMB zorunlu karşılık sayfası: {type(e).__name__}: {e}")
            L = {}
            sorun.append("sayfa")
        for k, u in L.items():
            try:
                dosya[k] = getir(s, u)
                time.sleep(1)
            except Exception as e:
                log(f"HATA {k} indirilemedi: {type(e).__name__}: {e}")
                sorun.append(k)
    pdfler = D.get("pdfler", {})
    for k, fn in (("tesis", tesis_pdf), ("arsiv", arsiv_xlsx), ("oran", oran_pdf), ("nema_tl", nema_tl), ("nema_yp", nema_yp), ("depo", depo_pdf)):
        if k not in dosya:
            if k not in sorun:
                sorun.append(k)
            continue
        try:
            v = fn(dosya[k])
            if k == "tesis":
                pdfler[v["bas"]] = v
                D["pdfler"] = pdfler
                log(f"   tesis: hesaplama {v['hesap']}, dönem {v['bas']}–{v['bit']}, ortalama {v['ort']} mr, bloke {v['bloke']} mr")
            else:
                D[k] = v
                if k == "arsiv":
                    log(f"   arşiv: {len(v['tl'])} TL dönemi, son {v['tl'][-1]['bas']}–{v['tl'][-1]['bit']}; ağırlıklı oran {len(v['oran'])} dönem")
                elif k == "oran":
                    log("   oranlar: " + "; ".join(f"{b} {x['teblig']} ({x['donem']}) {len(x['kalem'])} kalem{' [etiket tahmini]' if x['etiket_tahmini'] else ''}" for b, x in v.items()))
                elif k == "depo":
                    log(f"   döviz depo: {len(v['satir'])} satır, son {v['satir'][-1][0] if v['satir'] else '—'}")
                else:
                    log(f"   {k}: {len(v)} satır, son {v[0]['bas'] if v else '—'}")
        except Exception as e:
            log(f"HATA {k} ayrıştırılamadı: {type(e).__name__}: {e} — önceki veri korunuyor")
            sorun.append(k)
    # 2) EVDS
    seri = None
    if a.evds_json:
        seri = json.load(open(a.evds_json, encoding="utf-8"))
    else:
        anahtar = os.environ.get("EVDS_API_KEY")
        if anahtar:
            try:
                ev = evds_mod()
                R = ev(anahtar, ["TP.PPIBSM", "TP.PPIGBTL", "TP.APIFON4"], BAS, dt.date.today())
                seri = {d: {"bsm": v.get("TP.PPIBSM"), "gbl": v.get("TP.PPIGBTL"), "aof": v.get("TP.APIFON4")} for d, v in R.items()}
            except Exception as e:
                log(f"HATA EVDS: {type(e).__name__}: {e}")
                sorun.append("evds")
        else:
            log("EVDS_API_KEY yok")
            sorun.append("evds")
    if seri:
        aofs = [(d, v["aof"]) for d, v in sorted(seri.items()) if v.get("aof") is not None]
        if aofs:
            D["aof"] = {"tarih": aofs[-1][0], "oran": aofs[-1][1]}
        try:
            H = hesapla(seri, D.get("arsiv", {}), pdfler)
            if H:
                D.update(H)
                g = H["gunluk"]
                i = len(g["dates"]) - 1
                log(f"   günlük: {len(g['dates'])} gün; son {g['dates'][i]}: tesis {g['tesis'][i]} mr, ortalama tutulan {g['ortalama'][i]}, "
                    f"tutulması gereken {g['gereken'][i]}, serbest {g['serbest'][i]}, likidite durumu {g['likidite'][i]}")
        except Exception as e:
            log(f"HATA hesap: {type(e).__name__}: {e}")
            sorun.append("hesap")
    D["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    D["failed"] = sorun
    json.dump(D, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(cikti, "index.html"), "w", encoding="utf-8").write(open(os.path.join(KOK, "sayfa.html"), encoding="utf-8").read())
    log(f"yazıldı: {yol} ({os.path.getsize(yol) // 1024} KB)")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(KOK), "ortak"))
        from durum import yaz
        if D.get("gunluk", {}).get("dates"):
            yaz(a.site, "zk", D["gunluk"]["dates"][-1])
    except Exception as e:
        log(f"durum.json yazılamadı: {e}")
    log(f"TAMAM — sorunlu: {', '.join(sorun) or 'yok'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
