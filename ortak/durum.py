"""site/durum.json: her kaynağın en son veri tarihi (üst başlıktaki 'güncel' göstergesi için).

Yalnızca tarih tutar, veri içermez. Kullanım: from durum import yaz; yaz("site", "tefas", "2026-10-24")
"""
import datetime as dt
import json
import os


def yaz(site, anahtar, son_veri=None, **ek):
    yol = os.path.join(site, "durum.json")
    try:
        d = json.load(open(yol, encoding="utf-8"))
    except Exception:
        d = {}
    if son_veri is not None:
        d[anahtar] = {"son_veri": son_veri, "guncelleme": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    for k, v in ek.items():
        d[k] = v
    os.makedirs(site, exist_ok=True)
    json.dump(d, open(yol, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
