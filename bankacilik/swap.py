"""Yabancı swap stoku (haftalık): BDDK bilanço dışı yabancı para pozisyonu + TCMB ters swap stoku.

  Toplam yabancı swap stoku = BDDK BDYPP + TCMB ters swap
  - BDDK BDYPP: Haftalık Bülten › Yabancı Para Pozisyonu (tablo 297), Sektör, milyon USD,
    satır 4 "Bilanço Dışı Yabancı Para Pozisyonu (5-6)". Aynı tablodan bilanço içi pozisyon (1), net genel (7)
    ve yasal özkaynak (8) de tutulur.
  - TCMB ters swap: EVDS bie_swaptektarf › TP.SWAPTEKTAR.TOTALSTOKSATIMYONLU (TCMB taraflı swaplar, satım yönlü stok,
    milyon USD), bülten tarihindeki (yoksa ondan önceki son iş günü) değer.

Çıktı: site/makro/data/swap.json. BDDK'ya yük bindirmemek için her çalışmada en fazla EN_FAZLA hafta çekilir
(yeni haftalar önce, sonra geçmişe doğru 2021'e kadar); son hafta her seferinde tazelenir (düzeltme olabilir).
"""
import datetime as dt
import json
import os
import re
import time

import requests

TABLO = 297          # Yabancı Para Pozisyonu
SEKTOR = "10001"
ILK_YIL = 2021       # TCMB swap serisi 4 Ocak 2021'de başlıyor
EN_FAZLA = 40
TERS = "TP.SWAPTEKTAR.TOTALSTOKSATIMYONLU"


def _bddk(g, D, log):
    s = g.bddk_oturum()
    r = s.get(g.BDDK_H + "/", timeout=60)
    r.raise_for_status()
    p = g.Sayfa()
    p.feed(r.text)
    jeton = dict(p.jeton)
    donem = [(int(i), y) for i, y, _ in p.donem if i and y and int(y) >= ILK_YIL]
    if not donem:
        raise RuntimeError("haftalık bülten dönem listesi okunamadı")
    var = {int(k) for k in D["hafta"]}
    yeni = sorted([x for x in donem if x[0] not in var], key=lambda x: -x[0])
    son = max(var) if var else None
    hedef = ([x for x in donem if x[0] == son] if son else []) + yeni[:EN_FAZLA]
    log(f"   swap/BDDK: kayıtlı {len(var)} hafta, bu çalışmada {len(hedef)} hafta (kalan {max(0, len(yeni) - EN_FAZLA)})")

    def gonder(yol, alanlar):
        tok = jeton.get(yol)
        if not tok:
            raise RuntimeError(f"form jetonu yok: {yol}")
        rr = s.post("https://www.bddk.org.tr" + yol, data={"__RequestVerificationToken": tok, **alanlar}, timeout=60)
        rr.raise_for_status()
        pp = g.Sayfa()
        pp.feed(rr.text)
        jeton.update(pp.jeton)
        time.sleep(0.5)
        return pp

    for wid, yil in hedef:
        gonder("/BultenHaftalik/tr/Home/DonemDegistir", {"yil": yil, "donemId": str(wid), "para": "USD"})
        gonder("/BultenHaftalik/tr/Home/TarafSec", {"tarafKodu": SEKTOR})
        pp = gonder("/BultenHaftalik/", {"tabloId": str(TABLO)})
        if not pp.tablo:
            raise RuntimeError(f"tablo boş: hafta {wid}")
        baslik = pp.tablo[0][1] if len(pp.tablo[0]) > 1 else ""
        if "USD" not in baslik.upper() and "DOLAR" not in baslik.upper():
            raise RuntimeError(f"para birimi USD değil: {baslik[:120]}")
        m = re.search(r"(\d{1,2}) (\w+) (\d{4})", baslik)
        if not (m and m.group(2) in g.AYLAR):
            raise RuntimeError(f"hafta {wid} tarihi okunamadı: {baslik[:120]}")
        satir = {}
        for row in pp.tablo[1:]:
            if len(row) >= 3 and row[0].strip().isdigit():
                satir[row[0].strip()] = g.sayi(row[-1])
        if satir.get("4") is None:
            raise RuntimeError(f"hafta {wid}: bilanço dışı pozisyon satırı yok")
        D["hafta"][str(wid)] = {"t": f"{m.group(3)}-{g.AYLAR[m.group(2)]:02d}-{int(m.group(1)):02d}",
                                "ici": satir.get("1"), "disi": satir.get("4"), "net": satir.get("7"), "ozk": satir.get("8")}


def _ters(g, D, anahtar, log):
    s = requests.Session()
    s.headers.update({"key": anahtar, "User-Agent": g.UA})
    bugun = dt.date.today()
    bas = dt.date(ILK_YIL, 1, 1) if not D["ters"] else dt.date.fromisoformat(max(D["ters"])) - dt.timedelta(days=30)
    ham = g.evds_cek(s, [TERS], bas, bugun)
    for t, v in ham.items():
        if TERS in v:
            D["ters"][t] = v[TERS]
    log(f"   swap/TCMB ters swap: {len(D['ters'])} gün, son {max(D['ters']) if D['ters'] else '—'}")


def guncelle(g, site, anahtar, log):
    yol = os.path.join(site, "makro", "data", "swap.json")
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    try:
        eski = json.load(open(yol, encoding="utf-8"))
        D = {"hafta": eski.get("_hafta", {}), "ters": eski.get("_ters", {})}
    except Exception:
        D = {"hafta": {}, "ters": {}}
    sorun = []
    try:
        _bddk(g, D, log)
    except Exception as e:
        log(f"HATA swap/BDDK: {type(e).__name__}: {e} — önceki veri korunuyor")
        sorun.append("bddk")
    if anahtar:
        try:
            _ters(g, D, anahtar, log)
        except Exception as e:
            log(f"HATA swap/TCMB: {type(e).__name__}: {e} — önceki veri korunuyor")
            sorun.append("tcmb")
    else:
        sorun.append("tcmb")
    gunler = sorted(D["ters"])
    seri = []
    for wid in sorted(D["hafta"], key=int):
        h = D["hafta"][wid]
        once = [x for x in gunler if x <= h["t"]]
        tg = once[-1] if once and (dt.date.fromisoformat(h["t"]) - dt.date.fromisoformat(once[-1])).days <= 7 else None
        ters = D["ters"][tg] if tg else (0.0 if h["t"] < "2021-01-04" else None)
        seri.append({"id": int(wid), "t": h["t"], "disi": h["disi"], "ici": h["ici"], "net": h["net"], "ozk": h["ozk"],
                     "ters": ters, "ters_t": tg, "top": h["disi"] + ters if ters is not None and h["disi"] is not None else None})
    out = {"updated": g.simdi(), "birim": "milyon USD", "seri": seri, "failed": sorun,
           "kaynak": {"bddk": g.BDDK_H, "evds": "https://evds3.tcmb.gov.tr", "ters_kod": TERS},
           "_hafta": D["hafta"], "_ters": D["ters"]}
    json.dump(out, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    if seri:
        x = seri[-1]
        log(f"   swap: {len(seri)} hafta, son {x['t']} — BDYPP {x['disi']:,.0f} + ters swap {x['ters'] or 0:,.0f} = {x['top'] or 0:,.0f} mn USD")
    return sorun
