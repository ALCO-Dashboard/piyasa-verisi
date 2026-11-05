"""TCMB Veri Yayımlama Takvimi'ne göre güncelleme gerekip gerekmediğine karar verir.

Son güncellemeden (durum.json'daki "takvim_son") bu yana yayımlanmış, sitemizi ilgilendiren bir TCMB yayını
varsa (yayın saatinden 10 dk sonrası geçmişse) GITHUB_OUTPUT'a run=true yazar.
Kullanım: python ortak/takvim.py <durum.json yolu>
Takvimdeki saatler Türkiye saatidir (API sonuna "Z" eklese de).
"""
import datetime as dt
import json
import os
import sys

import requests

API = "https://appg.tcmb.gov.tr/igmvytsms-dis/veriTakvimi/list"
TR = dt.timezone(dt.timedelta(hours=3))
GECIKME = dt.timedelta(minutes=10)          # yayından sonra EVDS'ye düşmesi için pay
# Sitede kullandığımız EVDS verilerini ilgilendiren yayınlar (ad içinde geçen ifade)
ILGILI = ("Para ve Banka", "Faiz Oran", "Kâr Oran", "Kart", "Piyasa Katılımcıları", "Beklenti",
          "Rezerv", "Analitik Bilanço", "Vaziyet", "Swap", "Zorunlu Karşılık", "Menkul Kıymet", "Parasal", "Tüketici Fiyat", "Enflasyon")


def yayinlar(bas):
    """bas gününden itibaren (aynı ay ve, gerekirse, sonraki ay) yayınlar: [(zaman, ad)]."""
    out, gun = [], bas
    for _ in range(2):
        for sayfa in range(10):
            r = requests.get(API, params={"yil": gun.year, "ay": gun.month, "gun": gun.day, "lang": "tr", "page": sayfa, "size": 20},
                             headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=30)
            r.raise_for_status()
            j = r.json()
            for x in j.get("content") or []:
                t = dt.datetime.fromisoformat(x["tarih"][:19]).replace(tzinfo=TR)
                out.append((t, (x.get("yayinBilgi") or {}).get("yayimAdi") or ""))
            if sayfa + 1 >= (j.get("page") or {}).get("totalPages", 1):
                break
        if gun.month == dt.datetime.now(TR).month:
            break
        gun = (gun.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return out


def main():
    simdi = dt.datetime.now(TR)
    try:
        son = dt.datetime.fromisoformat(json.load(open(sys.argv[1], encoding="utf-8"))["takvim_son"])
    except Exception:
        son = simdi - dt.timedelta(hours=6)
    son = max(son, simdi - dt.timedelta(days=3))
    bekleyen = [(t, ad) for t, ad in yayinlar(son.date())
                if son < t + GECIKME <= simdi and any(k.lower() in ad.lower() for k in ILGILI)]
    for t, ad in bekleyen:
        print(f"Yayımlandı: {t:%d.%m %H:%M} {ad}")
    print(f"Son güncelleme {son:%d.%m %H:%M}, şimdi {simdi:%d.%m %H:%M}: {'güncelleme gerekli' if bekleyen else 'yeni yayın yok'}")
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as f:
        f.write(f"run={'true' if bekleyen else 'false'}\n")


if __name__ == "__main__":
    main()
