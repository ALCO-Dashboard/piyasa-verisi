"""Yatırım Vekaleti piyasa verisi: bankacilik/yv/*.xlsx (Piyasa İstihbarat tablosu) → EVDS biçiminde tek grup.

Tablo düzeni: 1. satır başlık (Para Birimi | Vadeler | Özel | Kamu | Özel | Kamu ...),
altında para birimi / vade satırları, "Tarih" satırında her Özel-Kamu çiftinin haftası.
Aynı hafta birden çok dosyada varsa adı alfabetik olarak sonra gelen (genelde daha yeni) dosya geçerli olur.
"""
import datetime as dt
import glob
import os
import re

KOD = "yv_piyasa"
PB = {"TRY": "TL", "TL": "TL", "USD": "ABD doları", "EUR": "Euro", "EURO": "Euro"}
TUR = {"ÖZEL": "Özel", "OZEL": "Özel", "KAMU": "Kamu"}


def _vade(v):
    v = str(v).strip()
    if v.upper() == "ON":
        return "ON", "ON (Gecelik)"
    m = re.match(r"(\d+)\s*(Ayl|Ay)", v, re.I)
    if m:
        return f"{m.group(1)}A", f"{m.group(1)} Ay Vadeli"
    return re.sub(r"\W+", "", v).upper() or "X", v


def _tarih(x):
    if isinstance(x, dt.datetime):
        return x.date().isoformat()
    if isinstance(x, dt.date):
        return x.isoformat()
    m = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", str(x or ""))
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def oku(yol):
    import openpyxl
    out = {}                                   # (kod, ad) -> {tarih: değer}
    wb = openpyxl.load_workbook(yol, data_only=True)
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        hi = next((i for i, r in enumerate(rows) if any(str(c or "").strip().lower() == "vadeler" for c in r)), None)
        ti = next((i for i, r in enumerate(rows) if str(r[0] or "").strip().lower() == "tarih"), None)
        if hi is None or ti is None:
            continue
        bas, tr = rows[hi], rows[ti]
        tarihler, son = {}, None
        for c in range(2, len(bas)):
            t = _tarih(tr[c]) if c < len(tr) else None
            son = t or son
            tarihler[c] = son
        pb = None
        for r in rows[hi + 1:ti]:
            if r[0] not in (None, ""):
                pb = PB.get(str(r[0]).strip().upper(), str(r[0]).strip())
            if r[1] in (None, "") or not pb:
                continue
            vk, vad = _vade(r[1])
            for c in range(2, min(len(r), len(bas))):
                tur = TUR.get(str(bas[c] or "").strip().upper())
                if not tur or tarihler.get(c) is None or not isinstance(r[c], (int, float)):
                    continue
                kod = f"YV.{ {'TL': 'TRY', 'ABD doları': 'USD', 'Euro': 'EUR'}.get(pb, pb) }.{vk}.{'OZEL' if tur == 'Özel' else 'KAMU'}"
                ad = f"{vad} ({pb}, {'Özel Bankalar' if tur == 'Özel' else 'Kamu Bankaları'}, %)"
                out.setdefault((kod, ad), {})[tarihler[c]] = float(r[c])
    return out


def derle(klasor):
    """Klasördeki tüm Excel'leri birleştirir; veri yoksa None."""
    seriler = {}
    for yol in sorted(glob.glob(os.path.join(klasor, "*.xls*"))):
        if os.path.basename(yol).startswith("~$"):
            continue
        try:
            for k, v in oku(yol).items():
                seriler.setdefault(k, {}).update(v)
        except Exception as e:
            print(f"UYARI: {os.path.basename(yol)} okunamadı: {e}", flush=True)
    if not seriler:
        return None
    sira = {"TRY": 0, "USD": 1, "EUR": 2}
    anahtar = lambda k: (sira.get(k[0].split(".")[1], 9), 0 if ".ON." in k[0] else int(re.sub(r"\D", "", k[0].split(".")[2]) or 99), k[0].endswith("KAMU"))
    ks = sorted(seriler, key=anahtar)
    tarihler = sorted({t for v in seriler.values() for t in v})
    return {"code": KOD, "name": "Yatırım Vekaleti Piyasa Verisi", "freq": "HAFTALIK(CUMA)", "unit": "Yüzde",
            "updated": dt.date.today().isoformat(), "kaynak": "Piyasa istihbaratı (Excel)",
            "series": [{"code": k, "name": a} for k, a in ks], "dates": tarihler,
            "vals": {k: [seriler[(k, a)].get(t) for t in tarihler] for k, a in ks}}
