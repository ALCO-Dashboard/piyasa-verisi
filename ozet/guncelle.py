"""Özet sekmesi: sitedeki diğer veri dosyalarından derlenen gösterge kartları, otomatik öne çıkanlar, risk ısı haritası,
BDDK haftalık kredi/mevduat değişimi, ForInvest haber akışından seçilmiş başlıklar ve veri takvimi.

Kaynaklar
  site/makro/data/{makro,ekonomi,bbg}.json, site/bankacilik/data/{politika,bddk_haftalik}.json,
  site/tcmb/data/tcmb.json, site/zk/data/zk.json  (diğer adımların yayımladığı veriler; burada yeniden çekilmez)
  ForInvest  https://www.foreks.com/llms-news.txt  (robots.txt ile yapay zekâ erişimine açık haber akışı; yalnızca başlık,
             saat ve bağlantı saklanır, haber metni alınmaz) ve llms-analysis.txt'deki günlük "Ekonomik Veri Takvimi"
             sayfaları (Türkiye ve yüksek önemli küresel veriler; her gün bir kez çekilir, önbellekte tutulur)
  TCMB Veri Yayımlama Takvimi API'si (appg.tcmb.gov.tr), PPK tarihleri (politika.json), ZK tesis dönemi (zk.json)

Çıktı: site/ozet/index.html, site/ozet/data/ozet.json
Kullanım: python ozet/guncelle.py --site site [--haber-dosya llms-news.txt] [--takvim-dosya takvim.json]
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys

import requests

KOK = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TR = dt.timezone(dt.timedelta(hours=3))
HABER_URL = "https://www.foreks.com/llms-news.txt"
TAKVIM_API = "https://appg.tcmb.gov.tr/igmvytsms-dis/veriTakvimi/list"
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def log(m):
    print(m, flush=True)


def oku(site, yol):
    try:
        return json.load(open(os.path.join(site, yol), encoding="utf-8"))
    except Exception as e:
        log(f"  {yol} okunamadı: {type(e).__name__}")
        return None


# ---------------------------------------------------------------- biçim yardımcıları
def ok(v):
    return isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))


def nf(v, d=1):
    if not ok(v):
        return "—"
    s = f"{abs(v):,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if v < 0 and round(abs(v), d) != 0 else "") + s


def sg(v, d=1):                       # işaretli sayı
    if not ok(v):
        return "—"
    r = round(v, d)
    return ("+" if r > 0 else "−" if r < 0 else "") + nf(abs(v), d)


def yuzde(v, d=1):
    return "—" if not ok(v) else ("−%" if v < 0 and round(v, d) != 0 else "%") + nf(abs(v), d)


def pyuzde(v, d=1):                   # işaretli yüzde
    if not ok(v):
        return "—"
    r = round(v, d)
    return ("+" if r > 0 else "−" if r < 0 else "") + "%" + nf(abs(v), d)


def ay_ad(m):                         # "2026-10" → "Ekim 2026"
    try:
        return f"{AYLAR[int(m[5:7]) - 1]} {m[:4]}"
    except Exception:
        return m or ""


def gun_ad(d):                        # "2026-11-06" → "6 Kasım"
    try:
        return f"{int(d[8:10])} {AYLAR[int(d[5:7]) - 1]}"
    except Exception:
        return d or ""


def q_ad(q):                          # "2026-Q2" → "2026 2. çeyrek"
    return f"{q[:4]} {q[6:]}. çeyrek" if q else ""


def son_i(vals):
    for i in range(len(vals) - 1, -1, -1):
        if ok(vals[i]):
            return i
    return -1


def ch(a, b):
    return (a / b - 1) * 100 if ok(a) and ok(b) and b else None


def roll(a, n):
    out = []
    for i in range(len(a)):
        w = a[i - n + 1:i + 1] if i >= n - 1 else []
        out.append(sum(w) if len(w) == n and all(ok(x) for x in w) else None)
    return out


def yon(v, iyi_artis):                # renk sınıfı: artış iyi mi kötü mü
    if not ok(v) or iyi_artis is None or abs(v) < 1e-9:
        return ""
    return "iyi" if (v > 0) == iyi_artis else "kotu"


def spark(vals, n=36):
    v = [round(x, 4) if ok(x) else None for x in vals[-n:]]
    return v if sum(1 for x in v if x is not None) >= 3 else None


def kart(k, ad, v, alt="", donem="", d=None, dc="", sp=None, link=None, kaynak=""):
    return {"k": k, "ad": ad, "v": v, "d": d, "dc": dc, "alt": alt, "donem": donem, "spark": sp, "link": link, "kaynak": kaynak}


def gunluk_seri(dates, vals):
    """[(tarih, değer)] yalnızca geçerli değerler."""
    return [(d, v) for d, v in zip(dates, vals) if ok(v)]


def once(seri, gun):
    """seri: [(tarih, değer)] artan; son tarihten 'gun' takvim günü önceki (ya da daha eski en yakın) değer."""
    if not seri:
        return None
    hedef = (dt.date.fromisoformat(seri[-1][0]) - dt.timedelta(days=gun)).isoformat()
    for d, v in reversed(seri):
        if d <= hedef:
            return v
    return None


def yuzdelik(seri, deger, gun=730):
    """deger'in son 'gun' günlük dağılımdaki yüzdeliği (0-100)."""
    if not seri or not ok(deger):
        return None
    sinir = (dt.date.fromisoformat(seri[-1][0]) - dt.timedelta(days=gun)).isoformat()
    xs = [v for d, v in seri if d >= sinir]
    if len(xs) < 20:
        return None
    return 100 * sum(1 for x in xs if x <= deger) / len(xs)


# ---------------------------------------------------------------- Bloomberg tabloları
def bbg_seri(B, tablo, etiket=None, ticker=None, alan="PX_LAST"):
    t = (B or {}).get("tablolar", {}).get(tablo)
    if not t:
        return []
    for j, k in enumerate(t.get("kolonlar") or []):
        if (etiket is None or k.get("etiket") == etiket) and (ticker is None or k.get("ticker") == ticker) and (k.get("alan") in (None, alan)):
            return gunluk_seri(t["dates"], t["v"][j])
    return []


# ---------------------------------------------------------------- Ekonomik göstergeler
def ekonomik(M, E, B):
    K, N = [], {}                      # kartlar, öne çıkanlar için sayılar
    t = (M or {}).get("tufe") or {}
    if t.get("months"):
        i = son_i(t["yoy"])
        dy = t["yoy"][i] - t["yoy"][i - 1] if i > 0 else None
        K.append(kart("tufe", "TÜFE (yıllık)", yuzde(t["yoy"][i], 2), f"aylık <b>{yuzde(t['mom'][i], 2)}</b>", ay_ad(t["months"][i]),
                      f"{sg(dy, 2)} puan" if ok(dy) else None, yon(dy, False), spark(t["yoy"]), "enf", "TÜİK"))
        N["tufe"] = dict(ay=t["months"][i], yoy=t["yoy"][i], dy=dy, mom=t["mom"][i], yoy_seri=t["yoy"], mom_seri=t["mom"])
    u = (M or {}).get("ufe") or {}
    if u.get("months"):
        i = son_i(u["yoy"])
        dy = u["yoy"][i] - u["yoy"][i - 1] if i > 0 else None
        K.append(kart("ufe", "Yİ-ÜFE (yıllık)", yuzde(u["yoy"][i], 2), f"aylık <b>{yuzde(u['mom'][i], 2)}</b>", ay_ad(u["months"][i]),
                      f"{sg(dy, 2)} puan" if ok(dy) else None, yon(dy, False), spark(u["yoy"]), "enf", "TÜİK"))
        N["ufe"] = dict(yoy=u["yoy"][i], ay=u["months"][i])
    b = (M or {}).get("beklenti") or {}
    if b.get("months") and b.get("pk_12ay"):
        i = son_i(b["pk_12ay"])
        dy = b["pk_12ay"][i] - b["pk_12ay"][i - 1] if i > 0 and ok(b["pk_12ay"][i - 1]) else None
        ys = b.get("pk_yilsonu", [None] * (i + 1))[i]
        K.append(kart("beklenti", "Enflasyon beklentisi (12 ay)", yuzde(b["pk_12ay"][i], 2), f"yıl sonu beklentisi <b>{yuzde(ys, 2)}</b>",
                      f"Piyasa Katılımcıları · {ay_ad(b['months'][i])}", f"{sg(dy, 2)} puan" if ok(dy) else None, yon(dy, False),
                      spark(b["pk_12ay"]), "enf", "TCMB"))
        N["beklenti"] = dict(v=b["pk_12ay"][i], ys=ys, ay=b["months"][i])
    if not E:
        return K, N
    Q = E.get("ceyrek") or {}
    if Q.get("dates") and Q.get("h_gsyh"):
        h = Q["h_gsyh"]
        i = son_i(h)
        yy = [ch(h[k], h[k - 4]) if k >= 4 else None for k in range(len(h))]
        qq = [ch(Q["mea"][k], Q["mea"][k - 1]) if k >= 1 else None for k in range(len(Q["mea"]))] if Q.get("mea") else []
        dy = yy[i] - yy[i - 1] if ok(yy[i]) and ok(yy[i - 1]) else None
        K.append(kart("gsyh", "GSYH büyümesi (yıllık)", pyuzde(yy[i]), f"çeyreklik (MEA) <b>{pyuzde(qq[i]) if qq else '—'}</b>", q_ad(Q["dates"][i]),
                      f"{sg(dy)} puan" if ok(dy) else None, yon(dy, True), spark(yy, 16), "buyume", "TÜİK"))
        N["gsyh"] = dict(q=Q["dates"][i], yy=yy[i], qq=qq[i] if qq else None, onceki=yy[i - 1])
    T = E.get("tuik") or {}
    I = T.get("isgucu") or {}
    if I.get("dates"):
        i = len(I["dates"]) - 1
        dy = I["issizlik"][i] - I["issizlik"][i - 1] if i > 0 else None
        G = T.get("genc") or {}
        gi = G.get("dates", []).index(I["dates"][i]) if I["dates"][i] in G.get("dates", []) else -1
        alt = f"genç (15-24) <b>{yuzde(G['issizlik'][gi])}</b>" if gi >= 0 else ""
        K.append(kart("issizlik", "İşsizlik oranı", yuzde(I["issizlik"][i]), alt, ay_ad(I["dates"][i]),
                      f"{sg(dy)} puan" if ok(dy) else None, yon(dy, False), spark(I["issizlik"]), "istihdam", "TÜİK"))
        N["issizlik"] = dict(v=I["issizlik"][i], dy=dy, ay=I["dates"][i])
    S = T.get("sanayi") or {}
    if S.get("dates") and S.get("bloklar"):
        bl = S["bloklar"][0]
        i = len(S["dates"]) - 1
        dy = bl["yoy"][i] - bl["yoy"][i - 1] if i > 0 and ok(bl["yoy"][i]) and ok(bl["yoy"][i - 1]) else None
        K.append(kart("sanayi", "Sanayi üretimi (yıllık)", pyuzde(bl["yoy"][i]), f"aylık (MEA) <b>{pyuzde(bl['mom'][i])}</b>", ay_ad(S["dates"][i]),
                      f"{sg(dy)} puan" if ok(dy) else None, yon(dy, True), spark(bl["yoy"]), "uretim", "TÜİK"))
        N["sanayi"] = dict(yoy=bl["yoy"][i], mom=bl["mom"][i], ay=S["dates"][i])
    pmi = bbg_seri(B, "PMI")
    if pmi:
        aylik = {}
        for d, v in pmi:
            aylik[d[:7]] = v
        ays = sorted(aylik)
        vs = [aylik[a] for a in ays]
        dy = vs[-1] - vs[-2] if len(vs) > 1 else None
        seri_n = 0
        for v in reversed(vs):
            if (v >= 50) == (vs[-1] >= 50):
                seri_n += 1
            else:
                break
        K.append(kart("pmi", "İmalat PMI", nf(vs[-1]), f"<b>{'büyüme' if vs[-1] >= 50 else 'daralma'}</b> bölgesi · eşik 50", ay_ad(ays[-1]),
                      sg(dy) if ok(dy) else None, yon(dy, True), spark(vs), "uretim", "İSO / Bloomberg"))
        N["pmi"] = dict(v=vs[-1], dy=dy, ay=ays[-1], seri_n=seri_n, tam=len(vs))
    A = E.get("aylik") or {}
    gsyh_usd = gsyh_tl = None
    if Q.get("c_gsyh"):
        j = son_i(Q["c_gsyh"])
        if j >= 3:
            gsyh_tl = sum(Q["c_gsyh"][j - 3:j + 1])
            kq = (E.get("kur") or {}).get("q") or {}
            try:
                gsyh_usd = sum(Q["c_gsyh"][k] / kq[Q["dates"][k]] for k in range(j - 3, j + 1)) / 1e6   # milyar $
            except Exception:
                gsyh_usd = None
    if A.get("dates") and A.get("cari"):
        c12 = roll(A["cari"], 12)
        j = son_i(c12)
        d12 = c12[j] - c12[j - 1] if ok(c12[j - 1]) else None
        oran = c12[j] / 1e3 / gsyh_usd * 100 if gsyh_usd else None
        K.append(kart("cari", "Cari denge (12 ay)", f"{nf(c12[j] / 1e3)} Mr $", f"GSYH'ya oranı <b>{yuzde(oran)}</b>" if ok(oran) else "",
                      ay_ad(A["dates"][j]), f"{sg(d12 / 1e3, 1)} Mr $" if ok(d12) else None, yon(d12, True),
                      spark([x / 1e3 if ok(x) else None for x in c12]), "dis", "TCMB"))
        N["cari"] = dict(v=c12[j] / 1e3, oran=oran, ay=A["dates"][j], aylik=A["cari"][j] / 1e3 if ok(A["cari"][j]) else None)
    if A.get("dates") and A.get("ihr") and A.get("ith"):
        j = son_i(A["ihr"])
        den = [(x - y) / 1e6 if ok(x) and ok(y) else None for x, y in zip(A["ihr"], A["ith"])]
        iy = ch(A["ihr"][j], A["ihr"][j - 12]) if j >= 12 else None
        K.append(kart("dis", "Dış ticaret dengesi", f"{nf(den[j])} Mr $", f"ihracat yıllık <b>{pyuzde(iy)}</b>", ay_ad(A["dates"][j]),
                      f"geçen yıl {nf(den[j - 12])} Mr $" if j >= 12 and ok(den[j - 12]) else None, "", spark(den, 24), "dis", "TÜİK / EVDS"))
        N["dis"] = dict(v=den[j], iy=iy, ay=A["dates"][j], ihr=A["ihr"][j] / 1e6)
    if A.get("dates") and A.get("b_gelir") and A.get("b_gider"):
        den = [x - y if ok(x) and ok(y) else None for x, y in zip(A["b_gelir"], A["b_gider"])]
        fd = [x - y if ok(x) and ok(y) else None for x, y in zip(A["b_gelir"], A.get("b_faizdisi_gider") or [None] * len(den))]
        d12, f12 = roll(den, 12), roll(fd, 12)
        j = son_i(d12)
        if j >= 0 and gsyh_tl:
            oran = d12[j] / gsyh_tl * 100
            fo = f12[j] / gsyh_tl * 100 if ok(f12[j]) else None
            onc = d12[j - 1] / gsyh_tl * 100 if ok(d12[j - 1]) else None
            dy = oran - onc if ok(onc) else None
            K.append(kart("butce", "Bütçe dengesi / GSYH (12 ay)", yuzde(oran), f"faiz dışı denge <b>{yuzde(fo)}</b>", ay_ad(A["dates"][j]),
                          f"{sg(dy, 2)} puan" if ok(dy) else None, yon(dy, True), spark([x / gsyh_tl * 100 if ok(x) else None for x in d12]), "butce", "HMB / EVDS"))
            N["butce"] = dict(oran=oran, fo=fo, ay=A["dates"][j], aylik=den[j] / 1e6 if ok(den[j]) else None)
    return K, N


# ---------------------------------------------------------------- Piyasa verileri
def piyasa(M, B, P, TC, Z, N):
    K = []
    simdi = dt.datetime.now(TR).date()
    # politika faizi
    fz = (P or {}).get("faiz") or []
    if fz:
        son, onc = fz[-1], (fz[-2] if len(fz) > 1 else None)
        dbp = (son["oran"] - onc["oran"]) * 100 if onc else None
        tufe = N.get("tufe", {}).get("yoy")
        bek = N.get("beklenti", {}).get("v")
        reel = ((1 + son["oran"] / 100) / (1 + tufe / 100) - 1) * 100 if ok(tufe) else None
        reel_b = ((1 + son["oran"] / 100) / (1 + bek / 100) - 1) * 100 if ok(bek) else None
        alt = f"reel getiri <b>{yuzde(reel)}</b> (TÜFE)" + (f" · <b>{yuzde(reel_b)}</b> (beklenti)" if ok(reel_b) else "")
        fs = []                                   # günlük politika faizi serisi (son 2 yıl)
        k = 0
        for gun in range(730, -1, -30):
            g = (simdi - dt.timedelta(days=gun)).isoformat()
            while k + 1 < len(fz) and fz[k + 1]["tarih"] <= g:
                k += 1
            fs.append(fz[k]["oran"] if fz[k]["tarih"] <= g else None)
        K.append(kart("faiz", "Politika faizi", yuzde(son["oran"], 2), alt, f"son karar {gun_ad(son['tarih'])} {son['tarih'][:4]}",
                      f"{sg(dbp, 0)} bp" if ok(dbp) else None, yon(dbp, None), spark(fs, 30), "pp", "TCMB"))
        N["faiz"] = dict(v=son["oran"], dbp=dbp, tarih=son["tarih"], reel=reel, reel_b=reel_b)
    # TLREF
    tl = (M or {}).get("tlref") or {}
    if tl.get("dates"):
        s = gunluk_seri(tl["dates"], tl["rate"])
        if s:
            w = once(s, 7)
            dbp = (s[-1][1] - w) * 100 if ok(w) else None
            K.append(kart("tlref", "TLREF", yuzde(s[-1][1], 2), f"BIST repo-ters repo gecelik referans", gun_ad(s[-1][0]),
                          f"{sg(dbp, 0)} bp/hafta" if ok(dbp) else None, "", spark([v for _, v in s], 60), "piyasa", "Borsa İstanbul"))
            N["tlref"] = dict(v=s[-1][1], dbp=dbp)
    # USD/TRY (EVDS döviz alış, günlük) + spot EUR/TRY (Bloomberg)
    dl = (P or {}).get("daily") or {}
    sr = dl.get("series") or {}
    if dl.get("dates") and sr.get("usdtry"):
        s = gunluk_seri(dl["dates"], sr["usdtry"])
        w = once(s, 7)
        dw = ch(s[-1][1], w)
        vi = ((B or {}).get("viop") or {}).get("kontratlar") or {}
        eur = (vi.get("EURTRY") or {}).get("spot")
        usd_spot = (vi.get("USDTRY") or {}).get("spot")
        alt = (f"spot <b>{nf(usd_spot, 4)}</b>" if ok(usd_spot) else "") + (f" · EUR/TRY <b>{nf(eur, 4)}</b>" if ok(eur) else "")
        K.append(kart("usdtry", "USD/TRY", nf(s[-1][1], 4), alt, f"TCMB döviz alış · {gun_ad(s[-1][0])}",
                      f"{pyuzde(dw, 2)}/hafta" if ok(dw) else None, yon(dw, False), spark([v for _, v in s], 60), "pp", "TCMB / Bloomberg"))
        N["usd"] = dict(v=s[-1][1], dw=dw, d30=ch(s[-1][1], once(s, 30)), seri=s)
    # BIST 100
    bi = bbg_seri(B, "Borsa Ve Diğer", ticker="XU100 Index")
    if bi:
        dw = ch(bi[-1][1], once(bi, 7))
        bk = bbg_seri(B, "Borsa Ve Diğer", ticker="XBANK Index")
        bkw = ch(bk[-1][1], once(bk, 7)) if bk else None
        K.append(kart("bist", "BIST 100", nf(bi[-1][1], 0), f"bankacılık endeksi <b>{pyuzde(bkw)}</b>/hafta" if ok(bkw) else "", gun_ad(bi[-1][0]),
                      f"{pyuzde(dw)}/hafta" if ok(dw) else None, yon(dw, True), spark([v for _, v in bi], 60), "piyasa", "Bloomberg"))
        N["bist"] = dict(v=bi[-1][1], dw=dw, bkw=bkw, seri=bi)
    # CDS
    cds = bbg_seri(B, "CDS", etiket="5Y CDS")
    if cds:
        w = once(cds, 7)
        dbp = cds[-1][1] - w if ok(w) else None
        K.append(kart("cds", "Türkiye 5Y CDS", f"{nf(cds[-1][1], 0)} bp", f"1 ay önce <b>{nf(once(cds, 30), 0)} bp</b>", gun_ad(cds[-1][0]),
                      f"{sg(dbp, 0)} bp/hafta" if ok(dbp) else None, yon(dbp, False), spark([v for _, v in cds], 60), "piyasa", "Bloomberg"))
        N["cds"] = dict(v=cds[-1][1], dbp=dbp, seri=cds)
    # tahvil
    t2 = bbg_seri(B, "TRY TAHVİL GÖSTERGE", etiket="2Y")
    t10 = bbg_seri(B, "TRY TAHVİL GÖSTERGE", etiket="10Y")
    if t2:
        w = once(t2, 7)
        dbp = (t2[-1][1] - w) * 100 if ok(w) else None
        alt = f"10 yıl <b>{yuzde(t10[-1][1], 2)}</b>" if t10 else ""
        K.append(kart("tahvil", "2 yıllık gösterge tahvil", yuzde(t2[-1][1], 2), alt, gun_ad(t2[-1][0]),
                      f"{sg(dbp, 0)} bp/hafta" if ok(dbp) else None, yon(dbp, False), spark([v for _, v in t2], 60), "piyasa", "Bloomberg"))
        N["tahvil"] = dict(v2=t2[-1][1], v10=t10[-1][1] if t10 else None, dbp=dbp, seri=t2)
    # Brent ve altın
    br = bbg_seri(B, "Borsa Ve Diğer", ticker="CO1 Comdty")
    if br:
        dw = ch(br[-1][1], once(br, 7))
        K.append(kart("brent", "Brent petrol", f"{nf(br[-1][1], 2)} $", f"1 ay <b>{pyuzde(ch(br[-1][1], once(br, 30)))}</b>", gun_ad(br[-1][0]),
                      f"{pyuzde(dw)}/hafta" if ok(dw) else None, yon(dw, False), spark([v for _, v in br], 60), "piyasa", "Bloomberg"))
        N["brent"] = dict(v=br[-1][1], dw=dw, seri=br)
    au = bbg_seri(B, "Kıymetli Maden", ticker="XAUUSD Curncy")
    if au:
        dw = ch(au[-1][1], once(au, 7))
        yb = next((v for d, v in reversed(au) if d < f"{au[-1][0][:4]}-01-01"), None)
        K.append(kart("altin", "Ons altın", f"{nf(au[-1][1], 0)} $", f"yılbaşından <b>{pyuzde(ch(au[-1][1], yb))}</b>", gun_ad(au[-1][0]),
                      f"{pyuzde(dw)}/hafta" if ok(dw) else None, "", spark([v for _, v in au], 60), "piyasa", "Bloomberg"))
        N["altin"] = dict(v=au[-1][1], dw=dw)
    # rezerv
    R = (TC or {}).get("rezerv") or {}
    if R.get("dates") and R.get("shn"):
        s = gunluk_seri(R["dates"], R["shn"])
        w = once(s, 7)
        dw = (s[-1][1] - w) / 1e3 if ok(w) else None
        bi_ = son_i(R["brut"])
        K.append(kart("rezerv", "Swap hariç net rezerv", f"{nf(s[-1][1] / 1e3)} Mr $", f"brüt rezerv <b>{nf(R['brut'][bi_] / 1e3)} Mr $</b>",
                      gun_ad(s[-1][0]) + " (tahmini)", f"{sg(dw)} Mr $/hafta" if ok(dw) else None, yon(dw, True),
                      spark([v / 1e3 for _, v in s], 60), "rezerv", "TCMB / hesaplama"))
        N["rezerv"] = dict(v=s[-1][1] / 1e3, dw=dw, brut=R["brut"][bi_] / 1e3, net=R["net"][son_i(R["net"])] / 1e3, seri=s)
    # ZK likidite + net fonlama
    g = (Z or {}).get("gunluk") or {}
    if g.get("dates") and g.get("likidite"):
        i = son_i(g["likidite"])
        dn = (Z.get("donemler") or [{}])[-1]
        net = None
        if sr.get("net"):
            j = son_i(sr["net"])
            net = sr["net"][j] / 1e3
        v = g["likidite"][i]
        alt = f"TCMB net fonlama <b>{nf(net, 0)} mr ₺</b>" if ok(net) else ""
        K.append(kart("likidite", "Piyasa likidite durumu", f"{sg(v, 0)} mr ₺", alt,
                      f"ZK dönemi {gun_ad(dn.get('bas', ''))}–{gun_ad(dn.get('bit', ''))}" if dn.get("bas") else gun_ad(g["dates"][i]),
                      "fazla" if v > 0 else "açık", "iyi" if v > 0 else "kotu",
                      spark([x for x in g["likidite"]], 60), "zk", "TCMB / hesaplama"))
        N["likidite"] = dict(v=v, net=net, bas=dn.get("bas"), bit=dn.get("bit"))
    return K


# ---------------------------------------------------------------- BDDK haftalık
def bddk(H, P):
    if not H or not H.get("values"):
        return None
    W = H["weeks"]
    ks = sorted((k for k in H["values"] if k in W), key=int)
    if len(ks) < 6:
        return None
    dl = (P or {}).get("daily") or {}
    kur = gunluk_seri(dl.get("dates") or [], (dl.get("series") or {}).get("usdtry") or [])

    def kur_t(t):
        v = None
        for d, x in kur:
            if d <= t:
                v = x
            else:
                break
        return v

    def deger(k, grup, tablo, satir, kol):
        try:
            return H["values"][k][grup][tablo][satir][kol]
        except Exception:
            return None

    son = ks[-1]
    yil = W[son][:4]
    yb = next((k for k in reversed(ks) if W[k] < f"{yil}-01-01"), None)
    KALEM = [  # (anahtar, ad, tablo, satır, para)
        ("kr_tp", "TL krediler", "krediler", "1", "tp"),
        ("kr_yp", "YP krediler ($)", "krediler", "1", "yp"),
        ("tk_tp", "Tüketici kredisi + kart (TL)", "krediler", "2", "tp"),
        ("tc_tp", "Ticari krediler (TL)", "krediler", "10", "tp"),
        ("mv_tp", "TL mevduat / katılım fonu", "mevduat", "1", "tp"),
        ("mv_yp", "YP mevduat / katılım fonu ($)", "mevduat", "1", "yp"),
    ]

    def stok(k, grup, tablo, satir, para):
        v = deger(k, grup, tablo, satir, 0 if para == "tp" else 1)
        if not ok(v):
            return None
        if para == "yp":
            kr = kur_t(W[k])
            return v / kr if kr else None        # milyon $
        return v                                  # milyon TL

    out = {"hafta": W[son], "onceki": W[ks[-2]], "yb": W[yb] if yb else None, "gruplar": {}, "seri": {"hafta": [W[k] for k in ks[-26:]]}}
    for grup in ("sektor", "katilim"):
        G = []
        for key, ad, tablo, satir, para in KALEM:
            s0, s1, s4 = stok(son, grup, tablo, satir, para), stok(ks[-2], grup, tablo, satir, para), stok(ks[-5], grup, tablo, satir, para)
            sy = stok(yb, grup, tablo, satir, para) if yb else None
            G.append({"k": key, "ad": ad, "stok": s0, "birim": "milyon $" if para == "yp" else "milyon TL",
                      "h": ch(s0, s1), "h4": ch(s0, s4), "yb": ch(s0, sy), "fark": (s0 - s1) if ok(s0) and ok(s1) else None})
            if key in ("kr_tp", "mv_tp", "kr_yp", "mv_yp"):
                ser = [stok(k, grup, tablo, satir, para) for k in ks[-27:]]
                out["seri"][f"{grup}_{key}"] = [round(ch(ser[i], ser[i - 1]), 3) if ok(ch(ser[i], ser[i - 1])) else None for i in range(1, len(ser))]
        kr = deger(son, grup, "krediler", "1", 2)
        mv = deger(son, grup, "mevduat", "1", 2)
        kr1 = deger(ks[-2], grup, "krediler", "1", 2)
        mv1 = deger(ks[-2], grup, "mevduat", "1", 2)
        kmo = kr / mv * 100 if ok(kr) and ok(mv) and mv else None
        kmo1 = kr1 / mv1 * 100 if ok(kr1) and ok(mv1) and mv1 else None
        out["gruplar"][grup] = {"kalem": G, "kmo": kmo, "kmo_d": kmo - kmo1 if ok(kmo) and ok(kmo1) else None,
                                "kredi_top": kr, "mevduat_top": mv}
    return out


# ---------------------------------------------------------------- öne çıkanlar ve risk
def one_cikanlar(N, BD, takvim):
    eko, piy = [], []

    def ekle(lst, metin, ton=""):
        lst.append({"m": metin, "t": ton})

    t = N.get("tufe")
    if t:
        yonm = "geriledi" if (t["dy"] or 0) < 0 else "yükseldi" if (t["dy"] or 0) > 0 else "değişmedi"
        m = f"Yıllık TÜFE {ay_ad(t['ay'])} ayında <b>{yuzde(t['yoy'], 2)}</b>"
        if ok(t["dy"]) and abs(t["dy"]) >= 0.005:
            m += f"; bir önceki aya göre {nf(abs(t['dy']), 2)} puan {yonm}"
        m += f". Aylık enflasyon {yuzde(t['mom'], 2)}"
        ms = [x for x in t["mom_seri"][-3:] if ok(x)]
        if len(ms) == 3:
            yil3 = (math.prod(1 + x / 100 for x in ms) ** 4 - 1) * 100
            m += f", son üç ayın yıllıklandırılmış hızı {yuzde(yil3)}"
        ekle(eko, m + ".", yon(t["dy"], False))
    bk = N.get("beklenti")
    if bk and t:
        fark = t["yoy"] - bk["v"]
        ekle(eko, f"Piyasa katılımcılarının 12 ay sonrası enflasyon beklentisi <b>{yuzde(bk['v'], 2)}</b>; yıl sonu beklentisi {yuzde(bk['ys'], 2)}. "
                  f"Beklenti mevcut enflasyonun {nf(abs(fark))} puan {'altında' if fark > 0 else 'üstünde'}.", "")
    g = N.get("gsyh")
    if g:
        ekle(eko, f"GSYH {q_ad(g['q'])} yıllık <b>{pyuzde(g['yy'])}</b> büyüdü (önceki çeyrek {pyuzde(g['onceki'])}); "
                  f"mevsimsellikten arındırılmış çeyreklik büyüme {pyuzde(g['qq'])}.", yon((g["yy"] or 0) - (g["onceki"] or 0), True))
    p = N.get("pmi")
    if p:
        bolge = "büyüme" if p["v"] >= 50 else "daralma"
        sure = f"üst üste {p['seri_n']}. ay" if p["seri_n"] < p["tam"] else f"veri setindeki tüm {p['tam']} ayda"
        ekle(eko, f"İmalat PMI {ay_ad(p['ay'])} ayında <b>{nf(p['v'])}</b>; sektör {sure} {bolge} bölgesinde.", "iyi" if p["v"] >= 50 else "kotu")
    s = N.get("sanayi")
    if s:
        ekle(eko, f"Sanayi üretimi {ay_ad(s['ay'])} ayında yıllık <b>{pyuzde(s['yoy'])}</b>, aylık {pyuzde(s['mom'])} değişti.", yon(s["yoy"], True))
    i = N.get("issizlik")
    if i:
        ekle(eko, f"İşsizlik oranı {ay_ad(i['ay'])} ayında <b>{yuzde(i['v'])}</b>"
                  + (f" ({sg(i['dy'])} puan)." if ok(i["dy"]) else "."), yon(i["dy"], False))
    c = N.get("cari")
    if c:
        ekle(eko, f"12 aylık cari denge <b>{nf(c['v'])} Mr $</b>" + (f" (GSYH'ya oranı {yuzde(c['oran'])})" if ok(c["oran"]) else "")
                  + (f"; {ay_ad(c['ay'])} ayında {nf(c['aylik'])} Mr $." if ok(c["aylik"]) else "."), yon(c["v"], True))
    b = N.get("butce")
    if b:
        ekle(eko, f"Bütçe açığı / GSYH (12 ay) <b>{yuzde(b['oran'])}</b>; faiz dışı denge {yuzde(b['fo'])}.", yon(b["oran"], True))

    f = N.get("faiz")
    if f:
        m = f"Politika faizi <b>{yuzde(f['v'], 2)}</b>"
        if ok(f["dbp"]):
            m += f"; son karar {gun_ad(f['tarih'])}: {sg(f['dbp'], 0)} bp"
        if ok(f["reel"]):
            m += f". TÜFE'ye göre reel getiri {yuzde(f['reel'])}"
        if ok(f["reel_b"]):
            m += f", 12 ay beklentisine göre {yuzde(f['reel_b'])}"
        ekle(piy, m + ".", "")
    ppk = next((x for x in takvim if x.get("tur") == "ppk" and x["gun"] >= 0), None)
    if ppk:
        ekle(piy, f"Sonraki PPK toplantısı <b>{gun_ad(ppk['tarih'])}</b> ({ppk['gun']} gün sonra).", "")
    hf = []
    if N.get("bist") and ok(N["bist"]["dw"]):
        hf.append(f"BIST 100 {pyuzde(N['bist']['dw'])}")
    if N.get("usd") and ok(N["usd"]["dw"]):
        hf.append(f"USD/TRY {pyuzde(N['usd']['dw'], 2)}")
    if N.get("cds") and ok(N["cds"]["dbp"]):
        hf.append(f"CDS {sg(N['cds']['dbp'], 0)} bp ({nf(N['cds']['v'], 0)} bp)")
    if N.get("tahvil") and ok(N["tahvil"]["dbp"]):
        hf.append(f"2Y tahvil {sg(N['tahvil']['dbp'], 0)} bp")
    if N.get("brent") and ok(N["brent"]["dw"]):
        hf.append(f"Brent {pyuzde(N['brent']['dw'])}")
    if hf:
        ekle(piy, "Son bir haftada: " + ", ".join(hf) + ".", "")
    r = N.get("rezerv")
    if r:
        m = f"Swap hariç net rezerv <b>{nf(r['v'])} Mr $</b> (tahmini)"
        if ok(r["dw"]):
            m += f"; bir haftada {sg(r['dw'])} Mr $"
        ekle(piy, m + f". Brüt rezerv {nf(r['brut'])} Mr $.", yon(r["dw"], True))
    lk = N.get("likidite")
    if lk:
        m = f"ZK tesis dönemi ({gun_ad(lk['bas'])}–{gun_ad(lk['bit'])}) hesabına göre piyasada <b>{nf(abs(lk['v']), 0)} mr ₺</b> likidite {'fazlası' if lk['v'] > 0 else 'açığı'} var"
        if ok(lk["net"]):
            m += f"; TCMB net fonlaması {nf(lk['net'], 0)} mr ₺"
        ekle(piy, m + ".", "")
    tv = N.get("tahvil")
    if tv and ok(tv.get("v10")):
        sp = (tv["v10"] - tv["v2"]) * 100
        ekle(piy, f"Getiri eğrisi: 2 yıllık {yuzde(tv['v2'], 2)}, 10 yıllık {yuzde(tv['v10'], 2)}; eğim <b>{sg(sp, 0)} bp</b> "
                  f"({'ters' if sp < 0 else 'pozitif'} eğri).", "")
    if BD:
        s, k = BD["gruplar"].get("sektor"), BD["gruplar"].get("katilim")
        al = lambda G, key: next((x for x in G["kalem"] if x["k"] == key), {})
        if s and k:
            ekle(piy, f"BDDK {gun_ad(BD['hafta'])} haftası: TL krediler sektörde <b>{pyuzde(al(s, 'kr_tp').get('h'), 2)}</b>, katılımda "
                      f"<b>{pyuzde(al(k, 'kr_tp').get('h'), 2)}</b>; TL mevduat sektörde {pyuzde(al(s, 'mv_tp').get('h'), 2)}, katılımda "
                      f"{pyuzde(al(k, 'mv_tp').get('h'), 2)} (haftalık).", "")
            ekle(piy, f"YP (dolar bazında) haftalık: krediler sektörde {pyuzde(al(s, 'kr_yp').get('h'), 2)}, katılımda {pyuzde(al(k, 'kr_yp').get('h'), 2)}; "
                      f"mevduat sektörde {pyuzde(al(s, 'mv_yp').get('h'), 2)}, katılımda {pyuzde(al(k, 'mv_yp').get('h'), 2)}.", "")
    return {"eko": eko, "piyasa": piy}


def seviye(skor):
    return "yuksek" if skor >= 75 else "orta" if skor >= 40 else "dusuk"


def riskler(N, BD):
    """Her gösterge için 0-100 risk skoru: piyasa serilerinde son 2 yılın yüzdeliği, makroda eşik kuralları."""
    R = []

    EKO = {"enf", "dis", "uretim", "istihdam", "butce", "buyume"}

    def ekle(ad, deger, skor, aciklama, link):
        if ok(skor):
            R.append({"ad": ad, "v": deger, "skor": round(max(0, min(100, skor))), "seviye": seviye(skor), "a": aciklama, "link": link,
                      "g": "e" if link in EKO else "p"})

    c = N.get("cds")
    if c:
        p = yuzdelik(c["seri"], c["v"])
        ekle("Ülke risk primi (CDS)", f"{nf(c['v'], 0)} bp", p, f"son 2 yılın {nf(p, 0)}. yüzdelik diliminde" if ok(p) else "", "piyasa")
    u = N.get("usd")
    if u and len(u["seri"]) > 300:
        lr = [math.log(u["seri"][k][1] / u["seri"][k - 1][1]) for k in range(1, len(u["seri"]))]
        vol = []
        for k in range(21, len(lr) + 1):
            w = lr[k - 21:k]
            m = sum(w) / 21
            vol.append((u["seri"][k][0], math.sqrt(sum((x - m) ** 2 for x in w) / 20) * math.sqrt(252) * 100))
        p = yuzdelik(vol, vol[-1][1])
        ekle("Kur oynaklığı (USD/TRY, 1 ay)", yuzde(vol[-1][1]), p, "yıllıklandırılmış günlük oynaklık; " + (f"son 2 yılın {nf(p, 0)}. yüzdelik diliminde" if ok(p) else ""), "pp")
    r = N.get("rezerv")
    if r:
        p = yuzdelik(r["seri"], r["v"] * 1e3)
        ekle("Rezerv yeterliliği (swap hariç net)", f"{nf(r['v'])} Mr $", 100 - p if ok(p) else None,
             f"son 2 yılın {nf(p, 0)}. yüzdelik diliminde (düşük rezerv = yüksek risk)" if ok(p) else "", "rezerv")
    tv = N.get("tahvil")
    if tv:
        p = yuzdelik(tv["seri"], tv["v2"])
        ekle("Faiz riski (2Y tahvil)", yuzde(tv["v2"], 2), p, f"son 2 yılın {nf(p, 0)}. yüzdelik diliminde" if ok(p) else "", "piyasa")
    br = N.get("brent")
    if br:
        p = yuzdelik(br["seri"], br["v"])
        ekle("Enerji fiyatı (Brent)", f"{nf(br['v'], 2)} $", p, f"son 2 yılın {nf(p, 0)}. yüzdelik diliminde" if ok(p) else "", "piyasa")
    t, f, bk = N.get("tufe"), N.get("faiz"), N.get("beklenti")
    if t:
        ms = [x for x in t["mom_seri"][-3:] if ok(x)]
        if len(ms) == 3:
            yil3 = (math.prod(1 + x / 100 for x in ms) ** 4 - 1) * 100
            fark = yil3 - t["yoy"]                     # pozitif: fiyat artış hızı yıllık enflasyonun üstünde (ivmelenme)
            ekle("Enflasyon ivmesi", f"3 ay yıllık. {yuzde(yil3)}", 50 + fark * 5,
                 f"son 3 ayın yıllıklandırılmış hızı yıllık enflasyonun {nf(abs(fark))} puan {'üstünde' if fark > 0 else 'altında'}", "enf")
    if f and bk and ok(f.get("reel_b")):
        rb = f["reel_b"]                               # beklentiye göre reel faiz: düştükçe risk artar
        ekle("Para politikası tamponu (ex-ante reel faiz)", yuzde(rb), 85 - rb * 7, "politika faizinin 12 ay enflasyon beklentisine göre reel karşılığı", "pp")
    lk = N.get("likidite")
    if lk and ok(lk["v"]):
        ekle("TL likidite (ZK hesabı)", f"{sg(lk['v'], 0)} mr ₺", 50 - lk["v"] / 20, "pozitif: piyasada fazla, negatif: açık", "zk")
    c = N.get("cari")
    if c and ok(c.get("oran")):
        ekle("Dış finansman ihtiyacı (cari / GSYH)", yuzde(c["oran"]), 30 - c["oran"] * 15, "12 aylık cari dengenin GSYH'ya oranı", "dis")
    p = N.get("pmi")
    if p:
        ekle("Reel sektör (imalat PMI)", nf(p["v"]), 50 + (50 - p["v"]) * 8, "50'nin altı daralma", "uretim")
    g = N.get("gsyh")
    if g and ok(g.get("yy")):
        ekle("Büyüme (GSYH, yıllık)", pyuzde(g["yy"]), 60 - g["yy"] * 8, "yavaşlama riski: büyüme düştükçe skor artar", "buyume")
    i = N.get("issizlik")
    if i and ok(i.get("v")):
        ekle("İşgücü piyasası (işsizlik)", yuzde(i["v"]), 50 + (i["v"] - 9) * 10 + (i["dy"] or 0) * 20, "işsizlik oranı ve son aydaki değişimi", "istihdam")
    b = N.get("butce")
    if b and ok(b.get("oran")):
        ekle("Mali disiplin (bütçe / GSYH)", yuzde(b["oran"]), 30 - b["oran"] * 10, "12 aylık bütçe dengesinin GSYH'ya oranı", "butce")
    if BD:
        s = BD["gruplar"].get("sektor")
        if s:
            h4 = next((x["h4"] for x in s["kalem"] if x["k"] == "kr_tp"), None)
            if ok(h4) and t:
                yil = ((1 + h4 / 100) ** 13 - 1) * 100
                fark = yil - t["yoy"]                  # reel kredi büyümesi (yıllıklandırılmış 4 hafta − TÜFE)
                ekle("TL kredi ivmesi (sektör)", f"4 hf yıllık. {yuzde(yil)}", 50 + fark * 2.5,
                     f"4 haftalık TL kredi büyümesinin yıllıklandırılmış hızı, TÜFE'nin {nf(abs(fark))} puan {'üstünde' if fark > 0 else 'altında'}", "bddk")
    R.sort(key=lambda x: -x["skor"])
    return R


# ---------------------------------------------------------------- haberler
KELIME = [  # (desen, puan, etiket, grup) — grup: p = Piyasa Verileri, e = Ekonomik Göstergeler sekmesinin gündemi
    (r"\bTCMB\b|Merkez Bankas|Karahan|\bPPK\b|politika faiz", 6, "TCMB", "p"),
    (r"\bTCMB\b|Merkez Bankas|Karahan|\bPPK\b|politika faiz", 3, "TCMB", "e"),
    (r"\bBDDK\b|zorunlu karşılık|katılım bank|katılım fon|Bankacılık Düzenleme", 6, "Bankacılık", "p"),
    (r"tahvil ihale|kira sertifikas|sukuk|borçlanma|DİBS|eurobond", 5, "Hazine ihale", "p"),
    (r"Hazine|Şimşek|Maliye Bakan|bütçe|nakit açığ|vergi|Orta Vadeli Program|\bOVP\b", 5, "Maliye", "e"),
    (r"enflasyon|TÜFE|ÜFE|\bfiyat artış|zam", 5, "Enflasyon", "e"),
    (r"enflasyon|TÜFE", 2, "Enflasyon", "p"),
    (r"Moody|Fitch|S&P|kredi not|\bCDS\b|risk prim", 6, "Kredi notu", "p"),
    (r"Moody|Fitch|S&P|kredi not", 3, "Kredi notu", "e"),
    (r"\bTÜİK\b|büyüme|GSYH|işsizlik|istihdam|cari (açık|denge|işlem)|ödemeler denge|dış ticaret|ihracat|ithalat|sanayi üretim|PMI|kapasite kullanım|güven endeks|perakende|konut satış|turizm|asgari ücret|IMF|OECD|Dünya Bankası", 5, "Makro veri", "e"),
    (r"\bSPK\b|fon soruşturma|gözaltı|soruşturma", 3, "Düzenleme", "p"),
    (r"rezerv|swap|likidite|mevduat|kredi büyüme|kredi faiz|kur korumal|\bKKM\b|repo", 4, "Bankacılık", "p"),
    (r"\bdolar\b|\bkur\b|Türk liras|\bTL\b|USD/TRY|döviz", 3, "Kur", "p"),
    (r"\bFed\b|Powell|ECB|Lagarde|BoJ|faiz karar|faiz artır|faiz indir|tahvil faiz", 3, "Küresel MB", "p"),
    (r"petrol|Brent|doğal gaz|Hürmüz|OPEC|enerji fiyat", 3, "Emtia / Jeopolitik", "p"),
    (r"petrol|doğal gaz|enerji fiyat|tarife|gümrük vergi|ticaret savaş", 2, "Küresel ekonomi", "e"),
    (r"İran|İsrail|Rusya|Ukrayna|savaş|saldırı|ateşkes|gerilim|yaptırım", 2, "Jeopolitik", "p"),
    (r"\bBIST\b|Borsa İstanbul|borsa|Wall Street", 1, "Piyasa", "p"),
    (r"altın", 1, "Emtia / Jeopolitik", "p"),
]
CEZA = [r"kar payı|kâr payı|temettü|bilanço|FAVÖK|net kar|zarardan|halka arz|bedelsiz|\bKAP\b|hisse(de|si|leri)? |sözleşme imzala|ihale kazan",
        r"Bitcoin|Ethereum|kripto|Binance|\bETF",
        r"PİYASAYA BAKIŞ|^Borsa güne|^Borsa günü"]


KURESEL = r"\bFed\b|ECB|Lagarde|\bBoJ\b|Ueda|Powell|Çin|\bABD\b|Japonya|İngiltere|Avrupa|Euro Bölgesi|Wall Street|Nasdaq|Dow Jones"
YERLI = r"Türk|TCMB|BDDK|Hazine|TÜİK|\bTL\b|Borsa İstanbul|\bBIST\b|\bSPK\b|Karahan|Şimşek|Ankara|katılım"


def haber_parse(metin):
    out = []
    for blok in re.split(r"\n(?=### )", metin):
        m = re.match(r"### (.+)", blok)
        tm = re.search(r"\*\*Tarih:\*\*\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", blok)
        um = re.search(r"\]\((https://www\.foreks\.com/haber/[^)\s]+)\)", blok)
        if m and tm and um:
            out.append({"b": re.sub(r"\s+", " ", m.group(1)).strip(), "t": tm.group(1), "u": um.group(1)})
    return out


def haber_puan(h, simdi, grup):
    b = h["b"]
    puan, etiket, best = 0, "", 0
    for desen, p, e, g in KELIME:
        if g == grup and re.search(desen, b, re.I):
            puan += p
            if p > best:
                best, etiket = p, e
    if best == 0:
        return -99, ""
    if re.search(KURESEL, b) and not re.search(YERLI, b, re.I):
        puan -= 2                                    # yalnızca yurt dışını ilgilendiren başlık
        etiket = "Küresel" if etiket not in ("Emtia / Jeopolitik", "Jeopolitik") else etiket
    for desen in CEZA:
        if re.search(desen, b, re.I):
            puan -= 6
    if re.search(r"\d+[,.]?\d*\s*(%|puan|baz puan|milyar|trilyon)|yüzde \d", b, re.I):
        puan += 1                                    # sayısal başlık: veri/karar haberi
    try:
        yas = (simdi - dt.datetime.strptime(h["t"], "%Y-%m-%d %H:%M").replace(tzinfo=TR)).total_seconds() / 3600
    except Exception:
        yas = 48
    puan -= max(0.0, yas) / 12                       # 12 saatte bir puan eskime
    return round(puan, 2), etiket


def haberler(onceki, metin):
    """Haber havuzunu günceller; her sekme (p: piyasa, e: ekonomi) için ayrı seçilmiş başlıklar döner."""
    simdi = dt.datetime.now(TR)
    havuz = {h["u"]: {"b": h["b"], "t": h["t"], "u": h["u"]} for h in (onceki or [])}
    for h in haber_parse(metin or ""):
        havuz[h["u"]] = {"b": h["b"], "t": h["t"], "u": h["u"]}
    sinir = (simdi - dt.timedelta(days=4)).strftime("%Y-%m-%d %H:%M")
    hepsi = sorted((h for h in havuz.values() if h["t"] >= sinir), key=lambda h: h["t"], reverse=True)
    out = {}
    for grup, ad in (("p", "piyasa"), ("e", "eko")):
        puanli = []
        for h in hepsi:
            p, e = haber_puan(h, simdi, grup)
            if p >= (3 if grup == "p" else 2):
                puanli.append({**h, "p": p, "e": e})
        secili, gorulen = [], {}
        for h in sorted(puanli, key=lambda h: -h["p"]):
            if len(secili) >= 7 or gorulen.get(h["e"], 0) >= 3:   # aynı konudan en fazla üç başlık
                continue
            gorulen[h["e"]] = gorulen.get(h["e"], 0) + 1
            secili.append(h)
        out[ad] = sorted(secili, key=lambda h: h["t"], reverse=True)
    return out, hepsi[:80]


# ---------------------------------------------------------------- takvim
TAKVIM_ONEMLI = [  # TCMB yayınlarından özetin takviminde gösterilecekler: (ad içinde geçen ifade, kısa ad, önem 1-3, sekme)
    ("Ödemeler Dengesi", "Ödemeler dengesi", 3, "e"), ("Piyasa Katılımcıları", "Piyasa Katılımcıları Anketi", 3, "pe"),
    ("Enflasyon Raporu", "Enflasyon Raporu", 3, "pe"), ("Finansal İstikrar", "Finansal İstikrar Raporu", 3, "p"),
    ("Kapasite Kullanım", "Kapasite kullanım oranı", 2, "e"), ("İktisadi Yönelim", "İktisadi yönelim / reel kesim güven", 2, "e"),
    ("Sektörel Enflasyon Beklenti", "Sektörel enflasyon beklentileri", 2, "e"), ("Uluslararası Rezervler", "Uluslararası rezervler (haftalık)", 2, "p"),
    ("Menkul Kıymet İstatistikleri", "Yurt dışı yerleşik menkul kıymet", 1, "p"), ("Reel Efektif", "Reel efektif döviz kuru", 1, "e"),
    ("Konut Fiyat", "Konut fiyat endeksi", 1, "e"), ("Dış Borç", "Dış borç istatistikleri", 1, "e"), ("Para ve Banka", "Para ve banka istatistikleri", 1, "p"),
    ("Analitik Bilanço", "TCMB analitik bilanço", 1, "p"), ("Fiyat Gelişmeleri", "Aylık fiyat gelişmeleri", 2, "e"),
    ("Zorunlu Karşılığa Tabi Katılım", "ZK'ya tabi katılım fonları", 1, "p"),
]


def tcmb_takvim(bas, bit, dosya=None):
    if dosya:
        j = json.load(open(dosya, encoding="utf-8"))
        hepsi = j.get("content", j) if isinstance(j, dict) else j
    else:
        hepsi, gun = [], bas.replace(day=1)
        while gun <= bit:
            for sayfa in range(10):
                r = requests.get(TAKVIM_API, params={"yil": gun.year, "ay": gun.month, "lang": "tr", "page": sayfa, "size": 20},
                                 headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30)
                r.raise_for_status()
                j = r.json()
                hepsi += j.get("content") or []
                if sayfa + 1 >= (j.get("page") or {}).get("totalPages", 1):
                    break
            gun = (gun + dt.timedelta(days=32)).replace(day=1)
    out, gor = [], set()
    for x in hepsi:
        ad = (x.get("yayinBilgi") or {}).get("yayimAdi") or ""
        bul = next(((k, o, g) for d, k, o, g in TAKVIM_ONEMLI if d.lower() in ad.lower()), None)
        if not bul:
            continue
        kisa, onem, grup = bul
        t = (x.get("tarih") or "")[:16]
        if not t or not (bas.isoformat() <= t[:10] <= bit.isoformat()):
            continue
        anahtar = (t[:10], kisa)
        if anahtar in gor:
            continue
        gor.add(anahtar)
        out.append({"tarih": t[:10], "saat": t[11:16], "ad": kisa, "donem": (x.get("donem") or "").replace(" Haftalık", "").strip(),
                    "kurum": "TCMB", "tur": "veri", "onem": onem, "g": grup, "url": (x.get("veriLink") or {}).get("link")})
    return out


FOREKS_ANALIZ = "https://www.foreks.com/llms-analysis.txt"
AY_NO = {a.lower(): i + 1 for i, a in enumerate(AYLAR)}
ESLES = [  # aynı yayını iki kaynakta tekilleştirmek için anahtar
    (r"cari işlem|ödemeler denge", "cari"), (r"rezerv", "rezerv"), (r"enflasyon rapor", "enfrapor"), (r"kapasite", "kko"),
    (r"piyasa katılımcı|beklenti anket", "pka"), (r"faiz karar|\bPPK\b", "ppk"), (r"reel kesim|iktisadi yönelim", "rkgo"),
]


def esles(ad):
    return next((k for d, k in ESLES if re.search(d, ad, re.I)), None)


def foreks_takvim_parse(sayfa):
    """'Ekonomik Veri Takvimi' haber sayfasındaki tablo → [{saat, ulke, ad, onem, beklenti, onceki}] (Türkiye + yüksek önemli)."""
    s = sayfa.replace('\\"', '"')
    m = re.search(r"<table>(.*?)</table>", s, re.S)
    if not m:
        return []
    temiz = lambda x: None if x.strip() in ("", "-", "undefined", "null") else re.sub(r"<[^>]+>", "", x).strip()
    out = []
    for r in re.findall(r'<tr>\s*<td>(.*?)</td>\s*<td>.*?alt="([^"]*)".*?</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>', m.group(1), re.S):
        saat, ulke, donem, ad, onem, bek, onc = r
        if ulke != "Türkiye" and onem != "Yüksek":
            continue
        out.append({"saat": temiz(saat), "ulke": ulke, "donem": temiz(donem), "ad": temiz(ad), "onem": onem, "beklenti": temiz(bek), "onceki": temiz(onc)})
    return out


def foreks_takvim(s, onbellek, metin=None, sayfalar=None):
    """ForInvest'in her gün için yayımladığı 'Ekonomik Veri Takvimi' sayfaları; önbellek: {tarih: {url, kalem}}."""
    import time
    bugun = dt.datetime.now(TR).date()
    ob = {d: v for d, v in (onbellek or {}).items() if d >= (bugun - dt.timedelta(days=10)).isoformat()}
    if metin is None:
        r = s.get(FOREKS_ANALIZ, timeout=30)
        r.raise_for_status()
        metin = r.text
    for blok in re.split(r"\n(?=### )", metin):
        m = re.match(r"### Ekonomik Veri Takvimi - (\d{1,2}) (\S+) (\d{4})", blok)
        um = re.search(r"\]\((https://www\.foreks\.com/haber/[^)\s]+)\)", blok)
        if not m or not um or m.group(2).lower() not in AY_NO:
            continue
        tarih = f"{m.group(3)}-{AY_NO[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
        if tarih < (bugun - dt.timedelta(days=10)).isoformat() or (ob.get(tarih) or {}).get("url") == um.group(1):
            continue
        try:
            if sayfalar is not None:
                html = sayfalar.get(um.group(1))
                if html is None:
                    continue
            else:
                time.sleep(3)                        # siteye yük bindirmemek için istekler aralıklı
                r = s.get(um.group(1), timeout=30)
                r.raise_for_status()
                html = r.text
            ob[tarih] = {"url": um.group(1), "kalem": foreks_takvim_parse(html)}
            log(f"  ForInvest takvim {tarih}: {len(ob[tarih]['kalem'])} kalem")
        except Exception as e:
            log(f"  ForInvest takvim {tarih} alınamadı: {type(e).__name__}: {e}")
    return dict(sorted(ob.items()))


def takvim(P, Z, FX, dosya=None):
    bugun = dt.datetime.now(TR).date()
    bas, bit = bugun - dt.timedelta(days=7), bugun + dt.timedelta(days=14)
    L = []
    try:
        L += tcmb_takvim(bas, bit, dosya)
    except Exception as e:
        log(f"  TCMB takvimi alınamadı: {type(e).__name__}: {e}")
    for yil, lst in ((P or {}).get("ppk") or {}).items():
        for x in lst:
            if bas.isoformat() <= x["tarih"] <= bit.isoformat():
                L.append({"tarih": x["tarih"], "saat": "14:00", "ad": "PPK faiz kararı", "donem": "", "kurum": "TCMB", "tur": "ppk", "onem": 3, "g": "pe", "url": x.get("url")})
            if x.get("ozet") and bas.isoformat() <= x["ozet"] <= bit.isoformat():
                L.append({"tarih": x["ozet"], "saat": "14:00", "ad": "PPK toplantı özeti", "donem": "", "kurum": "TCMB", "tur": "ppk_ozet", "onem": 2, "g": "pe", "url": None})
    for dn in ((Z or {}).get("donemler") or [])[-2:]:
        if dn.get("bit") and bas.isoformat() <= dn["bit"] <= bit.isoformat():
            L.append({"tarih": dn["bit"], "saat": "", "ad": "ZK tesis dönemi sonu", "donem": f"{gun_ad(dn['bas'])}–{gun_ad(dn['bit'])}",
                      "kurum": "TCMB", "tur": "zk", "onem": 2, "g": "p", "url": None})
            yeni = (dt.date.fromisoformat(dn["bit"]) + dt.timedelta(days=1)).isoformat()
            if yeni <= bit.isoformat():
                L.append({"tarih": yeni, "saat": "", "ad": "Yeni ZK tesis dönemi başlıyor", "donem": "", "kurum": "TCMB", "tur": "zk", "onem": 1, "g": "p", "url": None})
    var = {(x["tarih"], esles(x["ad"])) for x in L if esles(x["ad"])}
    for tarih, v in (FX or {}).items():
        if not (bas.isoformat() <= tarih <= bit.isoformat()):
            continue
        for k in v.get("kalem") or []:
            if not k.get("ad"):
                continue
            tr = k["ulke"] == "Türkiye"
            if tr and (tarih, esles(k["ad"])) in var:
                continue
            ek = "; ".join(x for x in ((f"beklenti {k['beklenti']}" if k.get("beklenti") else ""), (f"önceki {k['onceki']}" if k.get("onceki") else "")) if x)
            L.append({"tarih": tarih, "saat": k.get("saat") or "", "ad": k["ad"], "donem": ek, "kurum": "Türkiye" if tr else k["ulke"],
                      "tur": "tr" if tr else "dunya", "onem": (3 if k.get("onem") == "Yüksek" else 2) if tr else 2,
                      "g": "p" if re.search(r"faiz|rezerv|merkez bank|\bFed\b|ECB|tahvil|bono|ihale|swap", k["ad"], re.I) else "e", "url": v.get("url")})
    # sonraki PPK takvim penceresinin dışındaysa da (öne çıkanlar için) ekle
    gelecek = sorted(x["tarih"] for lst in ((P or {}).get("ppk") or {}).values() for x in lst if x["tarih"] > bit.isoformat())
    if gelecek and not any(x["tur"] == "ppk" and x["tarih"] >= bugun.isoformat() for x in L):
        L.append({"tarih": gelecek[0], "saat": "14:00", "ad": "PPK faiz kararı", "donem": "", "kurum": "TCMB", "tur": "ppk", "onem": 3, "g": "pe", "url": None, "uzak": True})
    for x in L:
        x["gun"] = (dt.date.fromisoformat(x["tarih"]) - bugun).days
    L.sort(key=lambda x: (x["tarih"], x["saat"] or "99"))
    return L


# ---------------------------------------------------------------- ana akış
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site")
    ap.add_argument("--haber-dosya", help="test: llms-news.txt yerel kopyası")
    ap.add_argument("--takvim-dosya", help="test: TCMB takvim API yanıtı (JSON)")
    ap.add_argument("--analiz-dosya", help="test: llms-analysis.txt yerel kopyası")
    ap.add_argument("--takvim-sayfa", nargs="*", help="test: ForInvest 'Ekonomik Veri Takvimi' sayfalarının yerel kopyaları")
    a = ap.parse_args()
    S = a.site
    cikti = os.path.join(S, "ozet")
    os.makedirs(os.path.join(cikti, "data"), exist_ok=True)
    yol = os.path.join(cikti, "data", "ozet.json")
    try:
        onceki = json.load(open(yol, encoding="utf-8"))
    except Exception:
        onceki = {}
    sorun = []
    M = oku(S, "makro/data/makro.json")
    E = oku(S, "makro/data/ekonomi.json")
    B = oku(S, "makro/data/bbg.json")
    P = oku(S, "bankacilik/data/politika.json")
    H = oku(S, "bankacilik/data/bddk_haftalik.json")
    TC = oku(S, "tcmb/data/tcmb.json")
    Z = oku(S, "zk/data/zk.json")

    eko, N = ekonomik(M, E, B)
    piy = piyasa(M, B, P, TC, Z, N)
    try:
        BD = bddk(H, P)
    except Exception as e:
        log(f"  BDDK özeti hesaplanamadı: {type(e).__name__}: {e}")
        BD = None
        sorun.append("bddk")
    s = requests.Session()                           # ForInvest dil yönlendirmesi çerez ister; oturum çerezi taşır
    s.headers.update({"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})
    metin = None
    if a.haber_dosya:
        metin = open(a.haber_dosya, encoding="utf-8").read()
    else:
        try:
            r = s.get(HABER_URL, timeout=30)
            r.raise_for_status()
            metin = r.text
        except Exception as e:
            log(f"  Haber akışı alınamadı: {type(e).__name__}: {e}")
            sorun.append("haber")
    secili, havuz = haberler(onceki.get("haber_havuz"), metin)
    try:
        if a.analiz_dosya:
            sayfalar = {}
            for f in a.takvim_sayfa or []:
                html = open(f, encoding="utf-8").read()
                um = re.search(r'https://www\.foreks\.com/haber/detay/[^"\s<>\\]+ekonomik-veri-takvimi[^"\s<>\\]*', html)
                if um:
                    sayfalar[um.group(0)] = html
            FX = foreks_takvim(s, onceki.get("foreks_takvim"), open(a.analiz_dosya, encoding="utf-8").read(), sayfalar)
        else:
            FX = foreks_takvim(s, onceki.get("foreks_takvim"))
    except Exception as e:
        log(f"  ForInvest ekonomik takvimi alınamadı: {type(e).__name__}: {e}")
        FX = onceki.get("foreks_takvim") or {}
        sorun.append("ekonomik takvim")
    tk = takvim(P, Z, FX, a.takvim_dosya)

    D = {
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "eko": eko, "piyasa": piy, "bddk": BD,
        "one_cikan": one_cikanlar(N, BD, tk),
        "risk": riskler(N, BD),
        "haber": secili, "haber_havuz": havuz,
        "haber_kaynak": {"ad": "ForInvest", "url": "https://www.foreks.com/haberler/"},
        "takvim": tk, "foreks_takvim": FX,
        "failed": sorun,
    }
    json.dump(D, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(cikti, "index.html"), "w", encoding="utf-8").write(open(os.path.join(KOK, "sayfa.html"), encoding="utf-8").read())
    log(f"Özet: {len(eko)} ekonomik, {len(piy)} piyasa kartı, {len(D['risk'])} risk, {len(secili['piyasa'])}+{len(secili['eko'])}/{len(havuz)} haber, {len(tk)} takvim kalemi"
        + (f"; sorun: {', '.join(sorun)}" if sorun else ""))
    try:
        sys.path.insert(0, os.path.join(KOK, "..", "ortak"))
        from durum import yaz
        yaz(S, "ozet", dt.datetime.now(TR).strftime("%Y-%m-%d"))
    except Exception as e:
        log(f"durum.json yazılamadı: {e}")


if __name__ == "__main__":
    main()
