"""Bloomberg Excel dosyası (BBG_Data_Excel.xlsm) → JSON.

Dosya parolasız yüklenebilir (veriler zaten sitede yayımlanıyor). Excel parolasıyla şifrelenmişse parola
BBG_ANAHTAR ortam değişkeninden alınır.

Tanınan sayfa düzenleri
  A) BDH tablosu: A1 "Start Date"; 4. satır ticker'lar, 5. satır vade/etiket, 6. satır alan, 7. satırdan itibaren
     A sütunu tarih, diğer sütunlar değer (sıralama artan ya da azalan olabilir).
  B) Tarih–değer çiftleri: 1. satır başlıklar "Tarih, Ad, Tarih, Ad, ..." (ör. BIST-REF, CDS).
  C) "BIST VIOP": 3. satır kontrat vadeleri, 4. satır ("Kontrat") vadeye kalan gün, altındaki satırlar
     kontrat başına ima edilen oran (ondalık); aşağıdaki bloklar ("<ad> | Ticker | ... | Volume") kontrat bazında
     son fiyat, açık pozisyon ve hacim.

Çıktılar
  --out       iş akışı içi tam çıktı (tcmb/guncelle.py altın fiyatını buradan alır)
  --site-out  sitede yayımlanan veri (makro/data/bbg.json)
Kullanım: python bloomberg/oku.py bloomberg/BBG_Data_Excel.xlsm --out bbg.json --site-out site/makro/data/bbg.json
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import sys

import openpyxl

ATLA = {"Ekran Yenileme"}


def ac(yol, parola):
    """Parolasız dosyayı doğrudan açar; Excel parolasıyla şifrelenmişse BBG_ANAHTAR ile çözer."""
    ham = open(yol, "rb").read()
    if ham[:4] == b"PK\x03\x04":
        return openpyxl.load_workbook(io.BytesIO(ham), data_only=True, read_only=True)
    if not parola:
        raise RuntimeError("Dosya parolalı ama BBG_ANAHTAR tanımlı değil")
    import msoffcrypto
    f = msoffcrypto.OfficeFile(io.BytesIO(ham))
    f.load_key(password=parola)
    out = io.BytesIO()
    try:
        f.decrypt(out)
    except Exception as e:
        raise RuntimeError(f"Dosya açılamadı — parola BBG_ANAHTAR ile aynı mı? ({type(e).__name__})")
    out.seek(0)
    return openpyxl.load_workbook(out, data_only=True, read_only=True)


def tarih(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:          # Excel seri numarası
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
    if isinstance(v, str):
        m = re.match(r"^\s*(\d{1,2})[./](\d{1,2})[./](\d{4})\s*$", v)
        if m:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", v)
        if m:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def sayi(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "."))
        except ValueError:
            return None
    return None


def metin(v):
    return v.strip() if isinstance(v, str) else ("" if v is None else str(v))


def tablo(kolonlar, satirlar):
    """kolonlar: [{etiket, ticker}], satirlar: {tarih: [değerler]} → artan tarihli tablo."""
    dates = sorted(satirlar)
    v = [[(round(satirlar[d][j], 6) if satirlar[d][j] is not None else None) for d in dates] for j in range(len(kolonlar))]
    keep = [j for j in range(len(kolonlar)) if any(x is not None for x in v[j])]
    return {"kolonlar": [kolonlar[j] for j in keep], "dates": [d.isoformat() for d in dates], "v": [v[j] for j in keep]}


def duzen_a(rows):
    tick, etk = rows[3], rows[4]
    kol = [(j, {"etiket": metin(etk[j]) or metin(tick[j]), "ticker": metin(tick[j])}) for j in range(1, len(tick)) if metin(tick[j])]
    sat = {}
    for r in rows[6:]:
        d = tarih(r[0]) if r else None
        if not d:
            continue
        vals = [sayi(r[j]) if j < len(r) else None for j, _ in kol]
        if any(x is not None for x in vals):
            sat[d] = vals
    return tablo([k for _, k in kol], sat)


def duzen_b(rows):
    bas = rows[0]
    ciftler = [(j, metin(bas[j + 1])) for j in range(len(bas) - 1) if metin(bas[j]).lower() == "tarih" and metin(bas[j + 1])]
    kol = [{"etiket": ad, "ticker": ""} for _, ad in ciftler]
    sat = {}
    for r in rows[1:]:
        for k, (j, _) in enumerate(ciftler):
            if j + 1 >= len(r):
                continue
            d, x = tarih(r[j]), sayi(r[j + 1])
            if d and x is not None:
                sat.setdefault(d, [None] * len(ciftler))[k] = x
    return tablo(kol, sat)


def viop(rows):
    out = {"tarih": None, "kontratlar": {}}
    if rows and rows[0] and len(rows[0]) > 1 and tarih(rows[0][1]):
        out["tarih"] = tarih(rows[0][1]).isoformat()
    ki = next((i for i, r in enumerate(rows) if r and metin(r[0]).lower() == "kontrat"), None)
    if ki is not None and ki >= 1:
        vade, gun = rows[ki - 1], rows[ki]
        for r in rows[ki + 1:]:
            ad = metin(r[0]) if r else ""
            if not ad:
                break
            kisa = ad.split()[0].upper()
            pts = []
            for j in range(2, len(r)):
                d, x = tarih(vade[j]) if j < len(vade) else None, sayi(r[j])
                if d and x is not None:
                    pts.append({"vade": d.isoformat(), "gun": int(sayi(gun[j]) or 0), "oran": round(x * 100, 4)})
            out["kontratlar"][kisa] = {"ticker": ad, "spot": sayi(r[1]) if len(r) > 1 else None, "egri": pts, "islem": []}
    i = 0
    while i < len(rows):
        r = rows[i]
        if r and len(r) > 1 and metin(r[1]).lower() == "ticker":
            kisa = metin(r[0]).split()[0].upper() if metin(r[0]) else ""
            bas = [metin(x).lower() for x in r]
            col = {k: bas.index(k) for k in ("lasttrade", "volume", "openint", "close", "time") if k in bas}
            i += 1
            while i < len(rows) and rows[i] and metin(rows[i][1] if len(rows[i]) > 1 else None):
                q = rows[i]
                d = tarih(q[0])
                g = lambda k: sayi(q[col[k]]) if k in col and col[k] < len(q) else None
                if d:
                    out["kontratlar"].setdefault(kisa, {"ticker": kisa, "spot": None, "egri": [], "islem": []})["islem"].append(
                        {"vade": d.isoformat(), "ticker": metin(q[1]), "son": g("lasttrade"), "kapanis": g("close"),
                         "hacim": g("volume"), "acik": g("openint"), "zaman": metin(q[col["time"]]) if "time" in col and col["time"] < len(q) else ""})
                i += 1
            continue
        i += 1
    return out


def oku(wb):
    T, V = {}, None
    for ws in wb.worksheets:
        if ws.title in ATLA:
            continue
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        if not rows:
            continue
        a1 = metin(rows[0][0]).lower() if rows[0] else ""
        try:
            if ws.title.upper().replace(" ", "") == "BISTVIOP":
                V = viop(rows)
            elif a1 == "start date" and len(rows) > 6:
                T[ws.title] = duzen_a(rows)
            elif a1 == "tarih":
                T[ws.title] = duzen_b(rows)
            else:
                print(f"   atlandı (düzen tanınmadı): {ws.title}")
        except Exception as e:
            print(f"UYARI {ws.title} okunamadı: {type(e).__name__}: {e}")
    tick = {}
    for t in T.values():
        for k, kol in enumerate(t["kolonlar"]):
            if kol["ticker"]:
                tick[kol["ticker"]] = {d: x for d, x in zip(t["dates"], t["v"][k]) if x is not None}
    return {"tablolar": T, "viop": V, "ticker": tick}


def dosya_bul(yol):
    """Dosya verilirse onu, klasör verilirse içindeki Excel'i (adı ne olursa olsun) döndürür."""
    if os.path.isfile(yol):
        return yol
    if not os.path.isdir(yol):
        return None
    adaylar = sorted(f for f in os.listdir(yol) if f.lower().endswith((".xlsm", ".xlsx")) and not f.startswith("~$"))
    oncelik = [f for f in adaylar if re.sub(r"[\s_]+", "", f.lower()).startswith("bbgdataexcel")]
    sec = (oncelik or adaylar)
    if len(sec) > 1:
        print("UYARI birden fazla Excel var, kullanılan:", sec[0], "— diğerleri:", ", ".join(sec[1:]))
    return os.path.join(yol, sec[0]) if sec else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", help="Excel dosyası ya da bloomberg klasörü")
    ap.add_argument("--out", required=True)
    ap.add_argument("--site-out", default="")
    a = ap.parse_args()
    yol = dosya_bul(a.xlsx)
    if not yol:
        print("Bloomberg Excel dosyası henüz yüklenmemiş")
        return 0
    try:
        D = oku(ac(yol, os.environ.get("BBG_ANAHTAR", "")))
        son = max((t["dates"][-1] for t in D["tablolar"].values() if t["dates"]), default=None)
        D["guncel"] = son
        for ad, t in D["tablolar"].items():
            print(f"   {ad:<24} {len(t['kolonlar']):>2} seri  {len(t['dates']):>4} gün  {t['dates'][0] if t['dates'] else '—'} – {t['dates'][-1] if t['dates'] else '—'}")
        if D["viop"]:
            print(f"   BIST VIOP {D['viop']['tarih']}: " + ", ".join(f"{k} ({len(v['egri'])} vade, {len(v['islem'])} kontrat)" for k, v in D["viop"]["kontratlar"].items()))
        json.dump(D, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        if a.site_out:
            os.makedirs(os.path.dirname(a.site_out), exist_ok=True)
            json.dump({"guncel": son, "tablolar": D["tablolar"], "viop": D["viop"],
                       "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
                      open(a.site_out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print(f"Bloomberg: {len(D['tablolar'])} tablo okundu, en yeni veri {son}")
        return 0
    except Exception as e:
        print(f"HATA Bloomberg dosyası: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
