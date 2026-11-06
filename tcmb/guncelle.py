"""TCMB sekmesi: Rezervler ve tahmini net müdahale.

Kaynaklar (hepsi TCMB EVDS)
  - Analitik bilanço (iş günü, bin TL): A02 dış varlıklar, A11 dış yükümlülükler, A13 kamu ve diğer döviz mevduatı,
    A14 bankalar döviz mevduatı
  - USD/TRY döviz alış (TP.DK.USD.A.YTL)
  - Haftalık vaziyet (Cuma, safi gram): rezerv altını (BL0021) ve TCMB'nin altın yükümlülükleri
    (bankalar: BL128 teminat, BL137 altın mevduatı, BL0891 zorunlu karşılık; Hazine BL0823; yurt dışı bankalar BL142)
  - Merkez Bankası rezervleri (haftalık, mn $): altın C1, döviz C2, toplam
  - TCMB taraflı swap stokları (iş günü, mn $): alım yönlü / satım yönlü toplam stok
  - Uluslararası rezervler ve döviz likiditesi tablosu (aylık): K14 yurt içi para karşılığı forward/swap net pozisyonu
  - Altın fiyatı: LBMA AM (TCMB rezerv altınını bu fiyatla değerler). Öncelik sırası:
      1) LBMA AM: goldsilver.com London Fix tablosu (LBMA fiyatları; GitHub'dan erişilebiliyor, LBMA'nın kendi
         sitesi erişimi engelliyor), tcmb/lbma_am.json (LBMA sitesinden elle alınanlar) ve varsa Bloomberg
         Excel'indeki GOLDLNAM Index
      2) Cuma günleri haftalık rezervden çıkan kesin fiyat: C1 / (BL0021 / 31,1034768)
      3) Borsa İstanbul altın USD/ons ağırlıklı ortalama (TP.ALTINPIYASA.AGORT03) — tahmini
Hesap
  net rezerv          = (A02 − A11 − A13 − A14) / kur
  swap hariç net      = net rezerv + K14 (son açıklanan ay sonu) − (alım yönlü stok değişimi) + (satım yönlü stok değişimi)
  altın fiyat etkisi  = (rezerv altını − altın yükümlülükleri, ons, önceki günün haftalık miktarı) × (P_t − P_{t−1})
  swap etkisi         = Δ alım yönlü stok − Δ satım yönlü stok
  net müdahale        = Δ net rezerv − altın fiyat etkisi − swap etkisi

Kullanım: python tcmb/guncelle.py --site site   (EVDS anahtarı EVDS_API_KEY ortam değişkeninden)
"""
import argparse
import bisect
import datetime as dt
import json
import os
import re
import sys
import time

import requests

KOK = os.path.dirname(os.path.abspath(__file__))
EVDS = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
BAS = dt.date(2023, 1, 2)
ONS = 31.1034768

GUNLUK = ["TP.AB.A02", "TP.AB.A11", "TP.AB.A13", "TP.AB.A14", "TP.DK.USD.A.YTL",
          "TP.SWAPTEKTAR.TOTALSTOKALIMYONLU", "TP.SWAPTEKTAR.TOTALSTOKSATIMYONLU", "TP.ALTINPIYASA.AGORT03"]
HAFTALIK_GR = {"rezerv": "TP.BL0021", "bnk_teminat": "TP.BL128", "bnk_mevduat": "TP.BL137", "bnk_zk": "TP.BL0891",
               "hazine": "TP.BL0823", "yurtdisi": "TP.BL142"}
HAFTALIK_USD = {"altin": "TP.AB.C1", "doviz": "TP.AB.C2", "toplam": "TP.AB.TOPLAM"}
AYLIK = {"k14": "TP.DOVVARNC.K14", "k15": "TP.DOVVARNC.K15", "k19": "TP.DOVVARNC.K19"}


def log(*a):
    print(*a, flush=True)


def simdi():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def evds(anahtar, kodlar, bas, bit, parca_gun=366):
    """{tarih: {kod: değer}}; tarih günlük/haftalık için YYYY-MM-DD, aylık için YYYY-MM."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "key": anahtar})
    out = {}
    while bas <= bit:
        son = min(bit, bas + dt.timedelta(days=parca_gun))
        url = EVDS + f"series={'-'.join(kodlar)}&startDate={bas:%d-%m-%Y}&endDate={son:%d-%m-%Y}&type=json"
        for deneme in range(4):
            try:
                r = s.get(url, timeout=120, allow_redirects=False)
                if r.status_code == 403:
                    raise RuntimeError("EVDS anahtarı reddedildi (EVDS_API_KEY)")
                r.raise_for_status()
                items = r.json().get("items", [])
                break
            except RuntimeError:
                raise
            except Exception as e:
                if deneme == 3:
                    raise
                log(f"   EVDS yeniden deneniyor ({type(e).__name__})")
                time.sleep(5 * (deneme + 1))
        for it in items:
            t = it.get("Tarih", "")
            m1 = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", t)
            m2 = re.match(r"^(\d{4})-(\d{1,2})$", t)
            if m1:
                k = f"{m1.group(3)}-{m1.group(2)}-{m1.group(1)}"
            elif m2:
                k = f"{m2.group(1)}-{int(m2.group(2)):02d}"
            else:
                continue
            for c in kodlar:
                v = it.get(c.replace(".", "_"))
                if v not in (None, "", "ND"):
                    try:
                        out.setdefault(k, {})[c] = float(v)
                    except (TypeError, ValueError):
                        pass
        bas = son + dt.timedelta(days=1)
        time.sleep(0.3)
    return out


def bbg_oku(yol):
    """bloomberg/oku.py çıktısı: ({"lbma_am": {tarih: değer}}, en yeni veri günü). GOLDLNAM Index herhangi bir
    sayfada (ör. ALTIN) BDH düzeninde olabilir."""
    j = json.load(open(yol, encoding="utf-8"))
    tk = j.get("ticker", {})
    am = tk.get("GOLDLNAM Index") or j.get("seriler", {}).get("lbma_am") or {}
    return {"lbma_am": am}, j.get("guncel") or j.get("dosya_tarihi")


AYLAR = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
GOLDSILVER = "https://goldsilver.com/price-charts/historical-london-fix/?selected_year={}"


def goldsilver(yillar):
    """goldsilver.com London Fix tablosu (LBMA'nın yayımladığı fiyatlar): {tarih: Gold AM}. Yıl başına bir istek."""
    out = {}
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "text/html"})
    for y in yillar:
        r = s.get(GOLDSILVER.format(y), timeout=60)
        r.raise_for_status()
        n = 0
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
            td = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(td) < 2:
                continue
            m = re.match(r"^(\d{1,2}) ([A-Z][a-z]{2}) (\d{4})$", td[0])
            if not m or m.group(2) not in AYLAR:
                continue
            try:
                v = float(td[1].replace(",", ""))
            except ValueError:
                continue
            out[f"{m.group(3)}-{AYLAR[m.group(2)]:02d}-{int(m.group(1)):02d}"] = v
            n += 1
        log(f"   goldsilver.com {y}: {n} gün")
        time.sleep(1.5)
    return out


def asof(tarihler, deger, t):
    """tarihler (sıralı) içinde t'den küçük/eşit son tarihin değeri."""
    i = bisect.bisect_right(tarihler, t) - 1
    return deger[tarihler[i]] if i >= 0 else None


def r1(v, n=1):
    return None if v is None else round(v, n)


def hesapla(G, H, A, lbma):
    # --- haftalık altın miktarları (milyon ons) ve resmi rezerv
    hft = sorted(t for t in H if H[t].get(HAFTALIK_GR["rezerv"]) is not None)
    q_res = {t: H[t][HAFTALIK_GR["rezerv"]] / ONS / 1e6 for t in hft}
    q_yuk = {t: sum(H[t].get(c) or 0 for k, c in HAFTALIK_GR.items() if k != "rezerv") / ONS / 1e6 for t in hft}
    q_bnk = {t: sum(H[t].get(HAFTALIK_GR[k]) or 0 for k in ("bnk_teminat", "bnk_mevduat", "bnk_zk")) / ONS / 1e6 for t in hft}
    p_cuma = {t: H[t][HAFTALIK_USD["altin"]] * 1e6 / (q_res[t] * 1e6) for t in hft
              if H[t].get(HAFTALIK_USD["altin"]) and q_res[t]}

    # --- günler: analitik bilanço kalemlerinin hepsi olan iş günleri
    gunler = sorted(t for t in G if all(G[t].get(c) is not None for c in GUNLUK[:4]))
    kur_t = sorted(t for t in G if G[t].get("TP.DK.USD.A.YTL"))
    kur = {t: G[t]["TP.DK.USD.A.YTL"] for t in kur_t}
    alim_t = sorted(t for t in G if G[t].get("TP.SWAPTEKTAR.TOTALSTOKALIMYONLU") is not None)
    alim = {t: G[t]["TP.SWAPTEKTAR.TOTALSTOKALIMYONLU"] for t in alim_t}
    sat_t = sorted(t for t in G if G[t].get("TP.SWAPTEKTAR.TOTALSTOKSATIMYONLU") is not None)
    sat = {t: G[t]["TP.SWAPTEKTAR.TOTALSTOKSATIMYONLU"] for t in sat_t}

    # --- altın fiyatı (USD/ons) ve kaynağı: L=LBMA, C=Cuma kesin (haftalık rezervden), B=BIST tahmini, =önceki gün
    fiyat, kaynak, onceki = {}, {}, None
    lbma_t = sorted(lbma)
    for t in gunler:
        i = bisect.bisect_right(lbma_t, t) - 1
        yakin = lbma_t[i] if i >= 0 and (dt.date.fromisoformat(t) - dt.date.fromisoformat(lbma_t[i])).days <= 5 and lbma_t[-1] > t else None
        if t in lbma:
            p, k = lbma[t], "L"
        elif t in p_cuma:
            p, k = p_cuma[t], "C"
        elif yakin:                                   # Londra tatili: TCMB son LBMA fiyatını kullanır
            p, k = lbma[yakin], "="
        elif G[t].get("TP.ALTINPIYASA.AGORT03"):
            p, k = G[t]["TP.ALTINPIYASA.AGORT03"], "B"
        else:
            p, k = onceki, "="
        fiyat[t], kaynak[t], onceki = p, k, p

    # --- K14 (aylık): ay sonu tarihini o ayın son bilanço günü say
    ay_sonu = {}
    for t in gunler:
        ay_sonu[t[:7]] = t
    k14 = sorted((ay_sonu[m], m, A[m][AYLIK["k14"]]) for m in A if A[m].get(AYLIK["k14"]) is not None and m in ay_sonu)
    k14_t = [x[0] for x in k14]

    out = {k: [] for k in ("dates", "kur", "a02", "a11", "a13", "a14", "brut", "net", "shn", "altin", "doviz",
                           "fiyat", "fk", "q_res", "q_net", "alim", "satim", "k14_ay", "degisim", "altin_etki",
                           "swap_etki", "mudahale")}
    on = None
    for t in gunler:
        kr = kur.get(t) or asof(kur_t, kur, t)
        if not kr:
            continue
        g = G[t]
        a02, a11, a13, a14 = (g[c] * 1e3 / kr / 1e6 for c in GUNLUK[:4])     # mn $
        net = a02 - a11 - a13 - a14
        al = asof(alim_t, alim, t) or 0.0
        sa = asof(sat_t, sat, t) or 0.0
        i = bisect.bisect_right(k14_t, t) - 1
        if i >= 0:
            bt, bay, bk = k14[i]
            shn = net + bk - (al - (asof(alim_t, alim, bt) or 0.0)) + (sa - (asof(sat_t, sat, bt) or 0.0))
        else:
            bay, shn = None, None
        qr, qn = asof(hft, q_res, t), None
        if qr is not None:
            qn = qr - (asof(hft, q_yuk, t) or 0.0)
        p = fiyat[t]
        altin = qr * p if qr is not None and p else None
        rec = dict(dates=t, kur=round(kr, 4), a02=r1(a02), a11=r1(a11), a13=r1(a13), a14=r1(a14), brut=r1(a02), net=r1(net),
                   shn=r1(shn), altin=r1(altin), doviz=r1(a02 - altin) if altin is not None else None, fiyat=r1(p, 2),
                   fk=kaynak[t], q_res=r1(qr, 3), q_net=r1(qn, 3), alim=r1(al), satim=r1(sa), k14_ay=bay,
                   degisim=None, altin_etki=None, swap_etki=None, mudahale=None)
        if on is not None:
            q_once = asof(hft, q_res, on["t"])
            qn_once = q_once - (asof(hft, q_yuk, on["t"]) or 0.0) if q_once is not None else None
            dn = net - on["net"]
            ae = qn_once * (p - on["p"]) if qn_once is not None and p and on["p"] else 0.0
            se = (al - on["al"]) - (sa - on["sa"])
            rec.update(degisim=r1(dn), altin_etki=r1(ae), swap_etki=r1(se), mudahale=r1(dn - ae - se))
        for k, v in rec.items():
            out[k].append(v)
        on = {"t": t, "net": net, "p": p, "al": al, "sa": sa}

    haftalik = {"dates": hft, **{k: [r1(H[t].get(c)) for t in hft] for k, c in HAFTALIK_USD.items()},
                "q_res": [r1(q_res[t], 3) for t in hft], "q_yuk": [r1(q_yuk[t], 3) for t in hft],
                "q_bnk": [r1(q_bnk[t], 3) for t in hft], "fiyat": [r1(p_cuma.get(t), 2) for t in hft]}
    aylar = sorted(m for m in A if A[m].get(AYLIK["k14"]) is not None)
    aylik = {"months": aylar, **{k: [A[m].get(c) for m in aylar] for k, c in AYLIK.items()}}
    return out, haftalik, aylik


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site")
    ap.add_argument("--bbg", default="", help="bloomberg/oku.py çıktısı (bbg.json)")
    a = ap.parse_args()
    anahtar = os.environ.get("EVDS_API_KEY", "")
    cikti = os.path.join(a.site, "tcmb")
    yol = os.path.join(cikti, "data", "tcmb.json")
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    try:
        D = json.load(open(yol, encoding="utf-8"))
    except Exception:
        D = {}
    bugun = dt.date.today()
    sorun = []
    try:
        if not anahtar:
            raise RuntimeError("EVDS_API_KEY yok")
        log("== günlük seriler")
        G = evds(anahtar, GUNLUK, BAS, bugun)
        log("== haftalık seriler")
        H = evds(anahtar, list(HAFTALIK_GR.values()) + list(HAFTALIK_USD.values()), BAS - dt.timedelta(days=60), bugun, 366 * 3)
        log("== aylık seriler")
        A = evds(anahtar, list(AYLIK.values()), BAS - dt.timedelta(days=400), bugun, 366 * 5)
        try:
            lbma = json.load(open(os.path.join(KOK, "lbma_am.json"), encoding="utf-8")).get("fiyat", {})
        except Exception as e:
            log(f"LBMA dosyası okunamadı: {e}")
            lbma = {}
        # goldsilver.com: ilk çalıştırmada 2023'ten itibaren tüm yıllar, sonra yalnızca bu yıl (Ocak'ta geçen yıl da)
        eski = D.get("lbma", {}) if isinstance(D.get("lbma"), dict) else {}
        yillar = list(range(BAS.year, bugun.year + 1)) if not any(k < f"{BAS.year}-02" for k in eski) else sorted({bugun.year, (bugun - dt.timedelta(days=20)).year})
        try:
            yeni = goldsilver(yillar)
            eski.update(yeni)
        except Exception as e:
            log(f"UYARI goldsilver.com okunamadı: {type(e).__name__}: {e} — kayıtlı LBMA fiyatlarıyla devam")
        D["lbma"] = dict(sorted(eski.items()))
        lbma = {**D["lbma"], **lbma}
        D.pop("bbg", None)
        if a.bbg and os.path.exists(a.bbg):
            try:
                bbg, zaman = bbg_oku(a.bbg)
                am = {t: v for t, v in (bbg.get("lbma_am") or {}).items() if v}
                lbma.update(am)
                D["bbg"] = {"zaman": zaman, "lbma_son": max(am) if am else None}
                log(f"   Bloomberg: {len(am)} günlük LBMA AM, son {max(am) if am else '—'} (dosya {zaman})")
            except Exception as e:
                log(f"UYARI Bloomberg verisi okunamadı: {type(e).__name__}: {e}")
        elif a.bbg:
            log("   Bloomberg verisi yok — LBMA dosyası ve EVDS fiyatıyla devam")
        g, h, m = hesapla(G, H, A, lbma)
        # kontrol: Cuma günleri haftalık rezervden çıkan TCMB değerleme fiyatı ile LBMA AM karşılaştırması
        fark = [abs(p - lbma[t]) for t, p in zip(h["dates"], h["fiyat"]) if p and t in lbma]
        if fark:
            log(f"   LBMA kontrol: {len(fark)} Cuma, ortalama fark {sum(fark) / len(fark):.2f} $, en büyük {max(fark):.2f} $")
        if len(g["dates"]) < 100:
            raise RuntimeError(f"beklenenden az gün ({len(g['dates'])})")
        D["rezerv"], D["haftalik"], D["aylik"] = g, h, m
        son = g["dates"][-1]
        fk = dict(zip(g["dates"], g["fk"]))
        log(f"   {len(g['dates'])} gün, son {son}; altın fiyatı kaynakları: "
            + ", ".join(f"{k}={sum(1 for v in fk.values() if v == k)}" for k in "LCB="))
    except Exception as e:
        log(f"HATA rezerv: {type(e).__name__}: {e} — önceki veri korunuyor")
        sorun.append("rezerv")
    D["updated"] = simdi()
    D["failed"] = sorun
    json.dump(D, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(cikti, "index.html"), "w", encoding="utf-8").write(open(os.path.join(KOK, "sayfa.html"), encoding="utf-8").read())
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(KOK), "ortak"))
        from durum import yaz
        if D.get("rezerv", {}).get("dates"):
            yaz(a.site, "rezerv", D["rezerv"]["dates"][-1])
    except Exception as e:
        log(f"durum.json yazılamadı: {e}")
    log(f"TAMAM — sorunlu: {', '.join(sorun) or 'yok'}")
    return 1 if sorun and not D.get("rezerv") else 0


if __name__ == "__main__":
    sys.exit(main())
