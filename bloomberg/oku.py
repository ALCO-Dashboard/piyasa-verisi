"""bloomberg/bloomberg.xlsx (BDH şablonu) → düz JSON.

Excel dosyası repo herkese açık olduğu için Excel'in kendi parolasıyla şifreli yüklenir; parola BBG_ANAHTAR
ortam değişkenindedir. Çıktı yalnızca iş akışının içinde kullanılır, yayımlanmaz.

Çıktı: {"dosya_tarihi": en yeni veri günü, "seriler": {anahtar: {"YYYY-MM-DD": değer}}, "meta": {anahtar: {...}}}
Kullanım: python bloomberg/oku.py bloomberg/bloomberg.xlsx --out bbg.json
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import sys

import openpyxl

ILK_SATIR = 3          # Tickerlar ve Veri sayfalarında ilk veri satırı


def ac(yol, parola):
    ham = open(yol, "rb").read()
    if ham[:4] == b"PK\x03\x04":
        raise RuntimeError("Dosya parolasız. Repo herkese açık olduğu için Bloomberg dosyası yalnızca parolayla "
                           "şifrelenmiş olarak okunur (Dosya → Bilgi → Çalışma Kitabını Koru → Parolayla Şifrele).")
    if not parola:
        raise RuntimeError("BBG_ANAHTAR tanımlı değil")
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
        m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", v.strip())
        if m:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def oku(wb):
    t = wb["Tickerlar"]
    meta, sira = {}, []
    for r in t.iter_rows(min_row=ILK_SATIR, values_only=True):
        no, ticker, anahtar, ad, grup, alan, birim = (list(r) + [None] * 8)[:7]
        if not isinstance(no, (int, float)):
            continue
        ticker = (ticker or "").strip() if isinstance(ticker, str) else ""
        anahtar = (anahtar or "").strip() if isinstance(anahtar, str) else ""
        if ticker and not anahtar:
            anahtar = re.sub(r"[^a-z0-9]+", "_", ticker.lower()).strip("_")
        sira.append((int(no), ticker, anahtar))
        if ticker:
            meta[anahtar] = {"ticker": ticker, "ad": ad or ticker, "grup": grup or "Diğer", "alan": alan or "PX_LAST", "birim": birim or ""}
    v = wb["Veri"]
    kolonlar = {}
    for r in v.iter_rows(min_row=ILK_SATIR, values_only=True):
        for no, ticker, anahtar in sira:
            if not ticker:
                continue
            i = 2 * (no - 1)
            if i + 1 >= len(r):
                continue
            d, x = tarih(r[i]), r[i + 1]
            if d and isinstance(x, (int, float)):
                kolonlar.setdefault(anahtar, {})[d.isoformat()] = round(float(x), 6)
    return {"seriler": kolonlar, "meta": meta}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        wb = ac(a.xlsx, os.environ.get("BBG_ANAHTAR", ""))
        D = oku(wb)
        D["dosya_tarihi"] = max((max(s) for s in D["seriler"].values() if s), default=None)     # en yeni veri günü
        bos = [k for k in D["meta"] if k not in D["seriler"]]
        for k, s in sorted(D["seriler"].items()):
            print(f"   {k:<14} {D['meta'][k]['ticker']:<18} {len(s):>5} gün  son {max(s)}  {s[max(s)]}")
        if bos:
            print("UYARI: verisi gelmeyen ticker'lar (formül dolmamış ya da ticker hatalı):",
                  ", ".join(D["meta"][k]["ticker"] for k in bos))
        json.dump(D, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print(f"Bloomberg: {len(D['seriler'])} seri okundu")
        return 0
    except Exception as e:
        print(f"HATA Bloomberg dosyası: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
