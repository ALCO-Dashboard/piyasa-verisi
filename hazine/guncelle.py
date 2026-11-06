"""Makro ve Piyasa → Makro Veriler → Hazine Borçlanma.

Kaynak: Hazine ve Maliye Bakanlığı, Kamu Finansmanı İstatistikleri (www.hmb.gov.tr/kamu-finansmani-istatistikleri).
Sayfa bir SPA; dosya bağlantıları portal API'sinden (/portal/v2/pages?slug=...) okunur. Dosya adlarının sonundaki
karma (hash) her güncellemede değiştiği için bağlantı her çalıştırmada yeniden bulunur.

Kullanılan dosyalar
  - Merkezi Yönetim İç Borç Stoku DİBS Listesi              → iç borç stoku (ISIN, valör, itfa, ihraç tipi, TL)
  - Merkezi Yönetim Dış Borç Stoku Tahvil Listesi           → yurt dışı tahvil/kira sertifikası stoku
  - Merkezi Yönetim İç Borç Ödeme Projeksiyonları (Aylık)  → 12 aylık anapara/faiz (milyon TL)
  - Merkezi Yönetim Dış Borç Ödeme Projeksiyonları (Aylık) → 12 aylık anapara/faiz (milyon ABD doları)
  - İç Borç Stokunun Elinde Bulunduranlara Göre Dağılımı   → aylık, milyar TL ve %

Kullanım: python hazine/guncelle.py --site site
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import time

import openpyxl
import requests

KOK = os.path.dirname(os.path.abspath(__file__))
API = "https://www.hmb.gov.tr/portal/v2/pages?slug=kamu-finansmani-istatistikleri"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
DOSYALAR = {
    "ic_stok": r"Ic_Borc_Stoku_DIBS_Listesi",
    "dis_stok": r"Dis_Borc_Stoku_Tahvil_Listesi",
    "ic_proj": r"Ic-Borc-Odeme-Projeksiyonlari-Aylik",
    "dis_proj": r"Dis_Borc_Odeme_Projeksiyonlari_Aylik",
    "sahip": r"Elinde_Bulunduranlara_Gore_Dagilimi",
}
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
AY_NO = {a.lower(): i + 1 for i, a in enumerate(AYLAR)}
# DİBS listesindeki bölüm başlığı → (kısa tür, para birimi grubu, faiz yapısı)
BOLUM = [
    (r"TL CİNSİ KUPONSUZ", "TL kuponsuz", "TL", "Sabit"),
    (r"TL CİNSİ SABİT FAİZLİ", "TL sabit kuponlu", "TL", "Sabit"),
    (r"TÜFE", "TÜFE'ye endeksli", "TL", "TÜFE"),
    (r"DEĞİŞKEN FAİZLİ", "TL değişken faizli", "TL", "Değişken"),
    (r"TLREFK", "TLREFK'ye endeksli kira sertifikası", "TL", "TLREF"),
    (r"TLREF", "TLREF'e endeksli", "TL", "TLREF"),
    (r"ALTINA DAYALI KİRA", "Altına dayalı kira sertifikası", "Altın", "Kira sertifikası"),
    (r"ALTIN TAHV", "Altın tahvili", "Altın", "Sabit"),
    (r"ABD DOLARI CİNSİ KİRA", "USD kira sertifikası", "USD", "Kira sertifikası"),
    (r"ABD DOLARI", "USD devlet tahvili", "USD", "Sabit"),
    (r"AVRO CİNSİ FAİZ ÖDEMESİZ", "EUR faiz ödemesiz", "EUR", "Faiz ödemesiz"),
    (r"AVRO", "EUR devlet tahvili", "EUR", "Sabit"),
    (r"TL CİNSİ FAİZ ÖDEMESİZ", "TL faiz ödemesiz", "TL", "Faiz ödemesiz"),
    (r"KİRA SERTİFİKASI", "TL kira sertifikası", "TL", "Kira sertifikası"),
]


def log(*a):
    print(*a, flush=True)


def tarih(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str):
        m = re.match(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})", v)
        if m:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def sayi(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def baglantilar(s):
    r = s.get(API, timeout=90)
    r.raise_for_status()
    metin = r.text.replace("\\/", "/")
    out = {}
    for k, desen in DOSYALAR.items():
        m = re.findall(r"https://ms\.hmb\.gov\.tr/uploads/[^\"'\s<>]*" + desen + r"[^\"'\s<>]*\.xlsx", metin)
        if m:
            out[k] = m[0]
    return out


def indir(s, url):
    for deneme in range(3):
        try:
            r = s.get(url, timeout=120)
            r.raise_for_status()
            return openpyxl.load_workbook(io.BytesIO(r.content), data_only=True, read_only=True)
        except Exception:
            if deneme == 2:
                raise
            time.sleep(5)


def ic_stok(wb):
    ws = wb.worksheets[0]                                 # en güncel yıl ilk sayfada
    R = [list(r) for r in ws.iter_rows(values_only=True)]
    itibar = None
    for r in R[:6]:
        for x in r:
            m = re.search(r"\((\d{1,2}) (\w+) (\d{4}) itibar", str(x or ""))
            if m and m.group(2).lower() in AY_NO:
                itibar = dt.date(int(m.group(3)), AY_NO[m.group(2).lower()], int(m.group(1))).isoformat()
    bolum, senetler, ihraclar, cur = None, [], [], None
    for r in R:
        b = r[1] if len(r) > 1 else None
        if isinstance(b, str) and b.strip() and not re.match(r"^\s*TR[A-Z0-9]{9,}", b) and b.strip() != "ISIN KODU":
            for desen, ad, para, faiz in BOLUM:
                if re.search(desen, b.upper()):
                    bolum = {"tur": ad, "para": para, "faiz": faiz}
                    break
            else:
                bolum = None if re.search(r"Soru|e-posta|Hazine ve Maliye", b, re.I) else {"tur": b.strip().title(), "para": "TL", "faiz": "Diğer"}
            continue
        if not bolum:
            continue
        isin = b.strip() if isinstance(b, str) and re.match(r"^\s*TR", b) else None
        valor, itfa, tip, tutar = tarih(r[2]), tarih(r[3]), (r[4] or "").strip() if isinstance(r[4], str) else "", sayi(r[5])
        if isin and itfa and tutar:                      # tek ihraçlı senet: aynı satırda
            cur = {"isin": isin, **bolum, "itfa": itfa.isoformat(), "tutar": tutar}
            senetler.append(cur)
            ihraclar.append({"isin": isin, **bolum, "valor": valor.isoformat() if valor else None, "itfa": itfa.isoformat(), "tip": tip, "tutar": tutar})
        elif isin and tutar:                             # çok ihraçlı senet: toplam satırı, altında ihraçlar
            cur = {"isin": isin, **bolum, "itfa": None, "tutar": tutar}
            senetler.append(cur)
        elif cur and itfa and tutar and not isin:
            cur["itfa"] = cur["itfa"] or itfa.isoformat()
            ihraclar.append({"isin": cur["isin"], **bolum, "valor": valor.isoformat() if valor else None, "itfa": itfa.isoformat(), "tip": tip, "tutar": tutar})
    senetler = [x for x in senetler if x["itfa"]]
    for x in senetler + ihraclar:                         # TRD… ISIN'ler kira sertifikası (sukuk)
        x["sukuk"] = x["isin"].startswith("TRD")
    return {"itibar": itibar, "senetler": senetler, "ihraclar": ihraclar}


def dis_stok(wb):
    R = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    itibar, satir = None, []
    for r in R:
        for x in r:
            m = re.search(r"(\d{2})\.(\d{2})\.(\d{4}) tarihi itibar", str(x or ""))
            if m and not itibar:
                itibar = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        a, i = tarih(r[1]), tarih(r[2])
        if a and i and len(r) > 9 and sayi(r[5]):
            tip = (r[8] or "").strip()
            satir.append({"anlasma": a.isoformat(), "itfa": i.isoformat(), "para": (r[4] or "").strip(), "tutar": sayi(r[5]),
                          "usd": sayi(r[6]), "kupon": sayi(r[7]), "tip": tip, "isin": (r[9] or "").strip(),
                          "tur": "Kira sertifikası" if "Kira" in tip else "Eurobond"})
    return {"itibar": itibar, "satir": satir}


def projeksiyon(wb):
    """Son projeksiyon ayının önümüzdeki 12 ayı: {ay: [...], anapara: [...], faiz: [...], zaman: 'YYYY-MM'}."""
    ws = wb.worksheets[-1]
    R = [list(r) for r in ws.iter_rows(values_only=True)]
    yil_r = next(i for i, r in enumerate(R) if any(isinstance(x, (int, float)) and 2000 < x < 2100 for x in r[3:]))
    ay_r = yil_r + 1
    kol, yil = {}, None
    for j in range(len(R[ay_r])):
        if j < len(R[yil_r]) and isinstance(R[yil_r][j], (int, float)) and 2000 < R[yil_r][j] < 2100:
            yil = int(R[yil_r][j])
        a = str(R[ay_r][j] or "").strip().lower()
        if yil and a in AY_NO:
            kol[j] = f"{yil}-{AY_NO[a]:02d}"
    sonuc = {}
    for bas in ("ANAPARA", "FAİZ"):
        i0 = next(i for i, r in enumerate(R) if str(r[1] or "").strip().upper().startswith(bas))
        pyil, son = None, None
        for i in range(i0, min(i0 + 13, len(R))):
            r = R[i]
            if isinstance(r[2], (int, float)):
                pyil = int(r[2])
            ay = str(r[3] or "").strip().lower()
            vals = {kol[j]: sayi(r[j]) for j in kol if j < len(r) and sayi(r[j]) is not None}
            if ay in AY_NO and len(vals) >= 6:
                son = (f"{pyil}-{AY_NO[ay]:02d}", vals)
        sonuc[bas] = son
    zaman = sonuc["ANAPARA"][0]
    aylar = sorted(set(sonuc["ANAPARA"][1]) | set(sonuc["FAİZ"][1]))
    return {"zaman": zaman, "ay": aylar, "anapara": [sonuc["ANAPARA"][1].get(a, 0) for a in aylar], "faiz": [sonuc["FAİZ"][1].get(a, 0) for a in aylar]}


def sahipler(wb, yil_sayisi=6):
    """Son yılların aylık sayfalarını birleştirir: {ay: [YYYY-MM], satir: [{ad, ust, mr: [...], pay: [...]}], son: index}."""
    yillar = sorted((ws for ws in wb.worksheets if str(ws.title).strip().isdigit()), key=lambda w: -int(w.title))[:yil_sayisi]
    veri, sira, ust = {}, [], {}
    for ws in yillar:
        yil = int(ws.title)
        R = [list(r) for r in ws.iter_rows(values_only=True)]
        bas = next(i for i, r in enumerate(R) if any(str(x or "").strip().lower() in AY_NO for x in r))
        aykol = [(j, AY_NO[str(x).strip().lower()]) for j, x in enumerate(R[bas]) if str(x or "").strip().lower() in AY_NO]
        for r in R[bas + 2:]:
            ad = next((x for x in r[:2] if isinstance(x, str) and x.strip()), None)
            if not ad:
                continue
            if ad.strip().startswith("("):
                break
            ad0 = re.sub(r"\s*\(\d\)\s*$", "", ad.strip())
            for j, ay in aykol:
                v = sayi(r[j]) if j < len(r) else None
                if v:
                    veri.setdefault(ad0, {})[f"{yil}-{ay:02d}"] = (v, sayi(r[j + 1]) if j + 1 < len(r) else None)
            if ad0 not in sira:
                sira.append(ad0)
                ust[ad0] = ad.strip().isupper()
    aylar = sorted({m for d in veri.values() for m in d})
    satir = [{"ad": k, "ust": ust[k], "mr": [veri[k].get(m, (None, None))[0] for m in aylar], "pay": [veri[k].get(m, (None, None))[1] for m in aylar]}
             for k in sira if k in veri]
    return {"ay": aylar, "satir": satir, "son": len(aylar) - 1 if aylar else None}


def cevrim(site, itibar):
    """Stok tarihindeki USD/TRY, EUR/TRY (TCMB döviz alış, EVDS) ve altın TL/gram (LBMA AM × USD/TRY; yoksa BIST AGORT03).
    DİBS listesinde döviz ve altın cinsi senetler TL karşılığıyla verildiği için USD ve ton karşılığı buradan bulunur."""
    anahtar = os.environ.get("EVDS_API_KEY")
    if not anahtar or not itibar:
        return None
    import importlib.util                                  # tcmb/guncelle.py içindeki EVDS okuyucu
    sp = importlib.util.spec_from_file_location("tcmb_guncelle", os.path.join(os.path.dirname(KOK), "tcmb", "guncelle.py"))
    tm = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(tm)
    evds, ONS = tm.evds, tm.ONS
    t = dt.date.fromisoformat(itibar)
    G = evds(anahtar, ["TP.DK.USD.A.YTL", "TP.DK.EUR.A.YTL", "TP.ALTINPIYASA.AGORT03"], t - dt.timedelta(days=10), t)
    gun = [d for d in sorted(G) if d <= itibar and G[d].get("TP.DK.USD.A.YTL")]
    if not gun:
        return None
    g = G[gun[-1]]
    usd, eur = g["TP.DK.USD.A.YTL"], g.get("TP.DK.EUR.A.YTL")
    ons, kaynak = None, None
    try:
        lb = json.load(open(os.path.join(site, "tcmb", "data", "tcmb.json"), encoding="utf-8")).get("lbma", {})
        k = [d for d in sorted(lb) if d <= itibar]
        if k and (t - dt.date.fromisoformat(k[-1])).days <= 5:
            ons, kaynak = lb[k[-1]], "LBMA AM " + k[-1]
    except Exception:
        pass
    if ons is None:
        a = [d for d in sorted(G) if d <= itibar and G[d].get("TP.ALTINPIYASA.AGORT03")]
        if a:
            ons, kaynak = G[a[-1]]["TP.ALTINPIYASA.AGORT03"], "BIST altın " + a[-1]
    if isinstance(ons, dict):
        ons = ons.get("usd") or next(iter(ons.values()), None)
    return {"tarih": gun[-1], "usd": usd, "eur": eur, "altin_gr": ons * usd / ONS if ons else None, "altin_ons_usd": ons, "altin_kaynak": kaynak}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site")
    a = ap.parse_args()
    yol = os.path.join(a.site, "makro", "data", "hazine.json")
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    try:
        D = json.load(open(yol, encoding="utf-8"))
    except Exception:
        D = {}
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    sorun = []
    try:
        lnk = baglantilar(s)
        log("bağlantılar:", ", ".join(f"{k}={os.path.basename(v)}" for k, v in lnk.items()))
    except Exception as e:
        log(f"HATA HMB sayfası okunamadı: {type(e).__name__}: {e}")
        lnk, sorun = {}, ["sayfa"]
    for k, fn in (("ic_stok", ic_stok), ("dis_stok", dis_stok), ("ic_proj", projeksiyon), ("dis_proj", projeksiyon), ("sahip", sahipler)):
        if k not in lnk:
            if "sayfa" not in sorun:
                sorun.append(k)
            continue
        try:
            D[k] = fn(indir(s, lnk[k]))
            D.setdefault("kaynak", {})[k] = lnk[k]
            ozet = {"ic_stok": lambda x: f"{len(x['senetler'])} senet, {len(x['ihraclar'])} ihraç, {x['itibar']}",
                    "dis_stok": lambda x: f"{len(x['satir'])} ihraç, {x['itibar']}",
                    "sahip": lambda x: f"{len(x['satir'])} satır, son {x['ay'][x['son']] if x['son'] is not None else '—'}"}.get(k, lambda x: f"{x['zaman']} projeksiyonu, {x['ay'][0]}–{x['ay'][-1]}")
            log(f"   {k}: {ozet(D[k])}")
            time.sleep(1)
        except Exception as e:
            log(f"HATA {k}: {type(e).__name__}: {e} — önceki veri korunuyor")
            sorun.append(k)
    try:
        c = cevrim(a.site, D.get("ic_stok", {}).get("itibar"))
        if c:
            D["cevrim"] = c
            log(f"   çevrim: {c['tarih']} USD {c['usd']}, EUR {c['eur']}, altın {c['altin_gr'] and round(c['altin_gr'], 1)} TL/gr ({c['altin_kaynak']})")
    except Exception as e:
        log(f"HATA kur/altın çevrimi: {type(e).__name__}: {e}")
        sorun.append("cevrim")
    D["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    D["failed"] = sorun
    json.dump(D, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(KOK), "ortak"))
        from durum import yaz
        if D.get("ic_stok", {}).get("itibar"):
            yaz(a.site, "hazine", D["ic_stok"]["itibar"])
    except Exception as e:
        log(f"durum.json yazılamadı: {e}")
    log(f"TAMAM — sorunlu: {', '.join(sorun) or 'yok'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
