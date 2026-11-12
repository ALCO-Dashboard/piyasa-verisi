"""Banka borçlanmaları (Makro ve Piyasa › Piyasa Verileri › Banka Borçlanmaları).

Üç kaynak tek dosyada toplanır → site/makro/data/borclanma.json
  1) BDDK Aylık Bülten (zaten çekilen veri): sendikasyon ve seküritizasyon kredileri (tablo 7), ihraç edilen menkul
     kıymetler, sermaye hesaplamasına dahil borçlanma araçları, bankalara borçlar (bilanço). Milyon TL; ay sonu
     TCMB döviz alış kuruyla milyon USD'ye de çevrilir.
  2) TCMB EVDS: dış borç çevirme oranı, bankaların uzun vadeli kredi kullanımı / anapara geri ödemesi, yurt dışı tahvil
     ihraç ve itfası, kısa vadeli dış borç stoku, kalan vadeye göre borç (aylık); bankaların eurobond stoku (haftalık).
  3) KAP: bankaların sendikasyon / yurt dışı kredi özel durum açıklamaları. Tutar, vade ve maliyet açıklama metninden
     ayrıştırılır. KAP'a yük bindirmemek için her çalışmada en fazla LISTE_EN_FAZLA liste sorgusu ve DETAY_EN_FAZLA
     bildirim sayfası istenir; geçmiş, çalışmadan çalışmaya geriye doğru tamamlanır (KAP_ILK'e kadar).
"""
import datetime as dt
import html as htmlmod
import json
import os
import re
import time

import requests

KAP = "https://www.kap.org.tr"
KAP_ILK = dt.date(2021, 1, 1)
PENCERE = 85              # gün; tüm bankalar tek sorguda, KAP yanıtı 2000 satırla sınırlı
LISTE_EN_FAZLA = 3        # çalışma başına geçmişe dönük liste sorgusu
DETAY_EN_FAZLA = 25       # çalışma başına bildirim sayfası
BEKLE = 2.5

EVDS_ILK = dt.date(2015, 1, 1)
AYLIK = {"roll_b": "TP.ODEROLL.K1", "roll_bt": "TP.ODEROLL.K3", "roll_d": "TP.ODEROLL.K2", "roll_dt": "TP.ODEROLL.K4",
         "kul": "TP.TEVDSUV.A3", "ode": "TP.TODEAPARA.A131", "tah_kul": "TP.ODEYDIEBS.A113", "tah_ode": "TP.ODEYDIEBS.A213",
         "kv": "TP.KVDB07", "kv_kredi": "TP.KVDB08", "kv_dth": "TP.KVDB09", "kv_mev": "TP.KVDB10", "kv_tl": "TP.KVDB11",
         "kal": "TP.KALANVADE.K5", "kal_kredi": "TP.KALANVADE.K6"}
HAFTALIK = {"eb": "TP.YDOSBAYAZDEG.S122T"}
KUR = {"usd": "TP.DK.USD.A.YTL", "eur": "TP.DK.EUR.A.YTL"}

# BDDK aylık bülten: (anahtar, tablo, satır, kolon)  — kolonlar TP, YP, Toplam
BDDK = [("send", "7", "1", 2), ("send_dt", "7", "2", 2), ("sek", "7", "3", 2),
        ("ihrac_yp", "1", "36", 1), ("ihrac_tp", "1", "36", 0), ("sbk_yp", "1", "41", 1), ("bank_yp", "1", "33", 1)]

RE_ADAY = re.compile(r"sendikasyon|syndicat|murabaha|seküritizasyon|securiti|\bdpr\b|kredi (temin|sözleşme|anlaşma|sağla)|kredi.*temin"
                     r"|yurt ?dışı.*(kredi|finansman)|kaynak temin|finansman temin", re.I)
RE_TUTAR = re.compile(r"(\d[\d.,]*)\s*(milyon|milyar)\s*(ABD\s*Dolar[ıi]|Amerikan\s*Dolar[ıi]|USD|Dolar|Avro|Euro|EUR)\b", re.I)
RE_VADE = re.compile(r"(\d[\d.]*)\s*gün(?:lük)?\s*vadeli|(\d+)\s*(yıl|ay)(?:\s*\d+\s*(?:iş\s*)?gün[üu]?)?\s*vadeli", re.I)
RE_MAL = re.compile(r"(SOFR|Euribor)\s*\+\s*%\s*(\d+(?:[.,]\d+)?)", re.I)


def _sayi(x):
    x = x.strip().rstrip(".,")
    if "," in x:
        x = x.replace(".", "").replace(",", ".")
    elif x.count(".") == 1 and len(x.split(".")[1]) == 3:      # 1.101 (binlik)
        x = x.replace(".", "")
    return float(x)


def ayristir(metin):
    """KAP açıklama metni → dilimler [{pb, tutar (mn), gun, maliyet}] ve yan bilgiler. Yalnızca Türkçe kalıplar eşleşir."""
    t = re.sub(r"\s+", " ", metin)
    vadeler = []
    for m in RE_VADE.finditer(t):
        if m.group(1):
            gun = int(m.group(1).replace(".", ""))
        else:
            gun = round(int(m.group(2)) * (365 if m.group(3).lower() == "yıl" else 30.44))
        vadeler.append((m.start(), gun))
    dilim = []
    for m in RE_TUTAR.finditer(t):
        once = t[max(0, m.start() - 28):m.start()].lower()
        if re.search(r"toplam|yaklaşık|karşılığı|eşdeğeri", once):      # dilimlerin toplamı; ayrı dilim değil
            continue
        try:
            v = _sayi(m.group(1)) * (1000 if m.group(2).lower() == "milyar" else 1)
        except ValueError:
            continue
        pb = "EUR" if re.match(r"avro|euro|eur", m.group(3), re.I) else "USD"
        cumle_sonu = t.find(". ", m.end())
        sonra = [g for p, g in vadeler if p >= m.end() and (cumle_sonu < 0 or p < cumle_sonu)]
        once_v = [g for p, g in vadeler if p < m.start()]
        gun = sonra[0] if sonra else (once_v[-1] if once_v else (vadeler[0][1] if vadeler else None))
        dilim.append({"pb": pb, "tutar": round(v, 3), "gun": gun, "maliyet": None, "_p": m.start()})
    # ilk maliyet cümlesinden sonra gelen tutarlar genelde tekrar/açıklamadır
    mal = [(m.start(), "USD" if m.group(1).lower() == "sofr" else "EUR", m.group(1).upper() if m.group(1).lower() == "sofr" else "Euribor",
            float(m.group(2).replace(",", "."))) for m in RE_MAL.finditer(t)]
    if mal:
        dilim = [d for d in dilim if d["_p"] < mal[0][0]] or dilim
    gunler = sorted({d["gun"] for d in dilim if d["gun"]})
    for p, pb, ad, sp in mal:
        once_v = [g for q, g in vadeler if q < p]
        gun = once_v[-1] if once_v else None
        hedef = [d for d in dilim if d["pb"] == pb and d["maliyet"] is None and (len(gunler) <= 1 or d["gun"] == gun)]
        if hedef:
            hedef[0]["maliyet"] = {"baz": ad, "bp": round(sp * 100)}
    for d in dilim:
        d.pop("_p", None)
    ek = {}
    m = re.search(r"(\d+)\s*ülkeden\s*(\d+)\s*(?:banka|finansal kurum|kurum)", t, re.I)
    if m:
        ek["ulke"], ek["kurum"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"%\s*(\d+)\s*(?:&#x27;|['’])?\s*[ıiuü]n üzerinde yenile|yenileme oranı\s*%\s*(\d+)|%\s*(\d+)\s*(?:oranında )?yenile", t, re.I)
    if m:
        ek["yenileme"] = int(next(x for x in m.groups() if x))
    if re.search(r"sürdürülebilir", t, re.I):
        ek["surd"] = True
    return dilim, ek


def _tur(ozet, metin=""):
    o = (ozet + " " + metin[:400]).lower()
    if "murabaha" in o:
        return "murabaha"
    if re.search(r"sendikasyon|syndicat", o):
        return "sendikasyon"
    if re.search(r"\bdpr\b|seküritizasyon|securiti|havale akım", o):
        return "dpr"
    return "diger"


def _oturum(g):
    s = requests.Session()
    s.headers.update({"User-Agent": g.UA, "Accept-Language": "tr"})
    return s


def _kap_liste(s, oids, bas, bit):
    govde = {"fromDate": bas.isoformat(), "toDate": bit.isoformat(), "memberType": "", "mkkMemberOidList": oids, "inactiveMkkMemberOidList": [],
             "disclosureClass": "ODA", "subjectList": [], "bdkMemberOidList": [], "mainSector": "", "sector": "", "subSector": "", "market": "", "index": "",
             "bdkReview": "", "isLate": "", "term": "", "ruleType": "", "period": "", "year": "", "fromSrc": False, "srcCategory": "", "discIndex": []}
    time.sleep(BEKLE)
    r = s.post(KAP + "/tr/api/disclosure/members/byCriteria", json=govde, timeout=120,
               headers={"Accept": "application/json", "Content-Type": "application/json", "Referer": KAP + "/tr/bildirim-sorgu"})
    r.raise_for_status()
    L = r.json()
    if not isinstance(L, list):
        raise RuntimeError(f"KAP beklenmeyen yanıt: {str(L)[:120]}")
    return L


def _kap_metin(s, bid):
    time.sleep(BEKLE)
    r = s.get(f"{KAP}/tr/Bildirim/{bid}", timeout=120)
    if r.status_code == 429:
        raise RuntimeError("KAP istek sınırı (429)")
    r.raise_for_status()
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S)
    t = htmlmod.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"\s+", " ", t)
    i = t.find("oda_ExplanationTextBlock|")
    if i < 0:
        i = t.find("oda_ExplanationSection|")
    if i < 0:
        return ""
    t = t[i:].split("|", 1)[1]
    j = t.find("Yukarıdaki açıklamalarımızın")
    return (t[:j] if j > 0 else t[:4000]).strip()


def _kap(g, K, log):
    """K = {"ham": {id: kayıt}, "bas": iso, "son": iso}"""
    s = _oturum(g)
    banka = {}
    for sek in ("BANKS", "PAR-BANKS"):
        time.sleep(1)
        r = s.get(f"{KAP}/tr/api/analysis/companies-by-sector/{sek}", headers={"Accept": "application/json"}, timeout=60)
        r.raise_for_status()
        for x in r.json():
            ad = x["company"].strip()
            if "VARLIK YÖNET" not in ad:
                banka[ad] = x["mkkMemberOid"]
    if len(banka) < 20:
        raise RuntimeError(f"KAP banka listesi eksik ({len(banka)})")
    bugun = dt.date.today()
    pencere = []
    son = dt.date.fromisoformat(K["son"]) if K.get("son") else None
    bas = dt.date.fromisoformat(K["bas"]) if K.get("bas") else None
    if son is None:
        pencere.append((bugun - dt.timedelta(days=PENCERE), bugun))
        bas = bugun - dt.timedelta(days=PENCERE)
    else:
        pencere.append((max(son - dt.timedelta(days=10), bugun - dt.timedelta(days=PENCERE)), bugun))
    b2 = bas
    for _ in range(LISTE_EN_FAZLA):
        if b2 <= KAP_ILK:
            break
        yeni = max(KAP_ILK, b2 - dt.timedelta(days=PENCERE))
        pencere.append((yeni, b2))
        b2 = yeni
    for a, b in pencere:
        L = _kap_liste(s, list(banka.values()), a, b)
        if len(L) >= 2000:
            log(f"   UYARI KAP: {a}→{b} penceresi 2000 satır sınırına ulaştı")
        n = 0
        for x in L:
            ad = (x.get("kapTitle") or "").strip()
            ozet = (x.get("summary") or "").strip()
            if ad not in banka or not (x.get("subject") or "").startswith("Özel Durum") or not RE_ADAY.search(ozet):
                continue
            bid = str(x["disclosureIndex"])
            if bid in K["ham"]:
                continue
            m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", x.get("publishDate") or "")
            if not m:
                continue
            kod = [c.strip() for c in (x.get("stockCodes") or "").split(",") if c.strip()]
            K["ham"][bid] = {"t": f"{m.group(3)}-{m.group(2)}-{m.group(1)}", "banka": ad, "kod": (sorted(kod, key=len)[-1] if kod else ""), "ozet": ozet, "metin": None}
            n += 1
        log(f"   KAP liste {a} → {b}: {len(L)} bildirim, {n} yeni aday")
        K["bas"] = min(a.isoformat(), K.get("bas") or a.isoformat())
        K["son"] = max(b.isoformat(), K.get("son") or b.isoformat())
    eksik = sorted((k for k, v in K["ham"].items() if v.get("metin") is None), key=lambda k: K["ham"][k]["t"], reverse=True)
    for bid in eksik[:DETAY_EN_FAZLA]:
        K["ham"][bid]["metin"] = _kap_metin(s, bid)
    log(f"   KAP: {len(K['ham'])} aday bildirim, metni bekleyen {max(0, len(eksik) - DETAY_EN_FAZLA)}, tarama {K.get('bas')} → {K.get('son')}")


def _kisa_ad(ad):
    ad = re.sub(r"\s+(A\.Ş\.|T\.A\.Ş\.|T\.A\.O\.)$", "", ad)
    tablo = {"TÜRKİYE GARANTİ BANKASI": "Garanti BBVA", "TÜRKİYE İŞ BANKASI": "İş Bankası", "YAPI VE KREDİ BANKASI": "Yapı Kredi", "TÜRKİYE VAKIFLAR BANKASI": "Vakıfbank",
             "T.C. ZİRAAT BANKASI": "Ziraat Bankası", "TÜRKİYE HALK BANKASI": "Halkbank", "QNB BANK": "QNB", "TÜRK EKONOMİ BANKASI": "TEB", "AKBANK": "Akbank",
             "TÜRKİYE SINAİ KALKINMA BANKASI": "TSKB", "TÜRKİYE İHRACAT KREDİ BANKASI": "Türk Eximbank", "TÜRKİYE KALKINMA VE YATIRIM BANKASI": "TKYB",
             "KUVEYT TÜRK KATILIM BANKASI": "Kuveyt Türk", "ALBARAKA TÜRK KATILIM BANKASI": "Albaraka Türk", "TÜRKİYE FİNANS KATILIM BANKASI": "Türkiye Finans",
             "VAKIF KATILIM BANKASI": "Vakıf Katılım", "ZİRAAT KATILIM BANKASI": "Ziraat Katılım", "TÜRKİYE EMLAK KATILIM BANKASI": "Emlak Katılım",
             "DENİZBANK": "Denizbank", "ŞEKERBANK": "Şekerbank", "FİBABANKA": "Fibabanka", "ODEA BANK": "Odeabank", "ALTERNATİFBANK": "Alternatif Bank",
             "ANADOLUBANK": "Anadolubank", "BURGAN BANK": "Burgan Bank", "ING BANK": "ING", "AKTİF YATIRIM BANKASI": "Aktif Bank"}
    return tablo.get(ad, ad.title())


def _kap_cikti(K, kur):
    """Ayrıştırılmış işlem listesi (yeniden eskiye)."""
    gunler = sorted(kur)

    def capraz(t):
        once = [x for x in gunler if x <= t]
        k = kur.get(once[-1]) if once else None
        return k["eur"] / k["usd"] if k and k.get("usd") and k.get("eur") else None

    out = []
    for bid, v in K["ham"].items():
        if v.get("metin") is None:
            continue
        dilim, ek = ayristir(v["metin"])
        usd = sum(d["tutar"] for d in dilim if d["pb"] == "USD")
        eur = sum(d["tutar"] for d in dilim if d["pb"] == "EUR")
        c = capraz(v["t"])
        top = usd + eur * c if (c or not eur) else None
        out.append({"id": int(bid), "t": v["t"], "banka": _kisa_ad(v["banka"]), "kod": v["kod"], "tur": _tur(v["ozet"], v["metin"]), "ozet": v["ozet"],
                    "dilim": dilim, "usd": round(usd, 2), "eur": round(eur, 2), "top": round(top, 1) if top else None,
                    "metin": v["metin"][:900], **ek})
    return sorted(out, key=lambda x: (x["t"], x["id"]), reverse=True)


def _evds(g, E, anahtar, log):
    s = requests.Session()
    s.headers.update({"key": anahtar, "User-Agent": g.UA})
    bugun = dt.date.today()
    ters = {v: k for k, v in AYLIK.items()}
    bas = EVDS_ILK if not E["aylik"] else dt.date.fromisoformat(max(E["aylik"]) + "-01") - dt.timedelta(days=400)   # geriye dönük revizyonlar
    for t, v in g.evds_cek(s, list(AYLIK.values()), bas, bugun, aylik=True).items():
        E["aylik"].setdefault(t, {}).update({ters[c]: x for c, x in v.items() if c in ters})
    ters = {v: k for k, v in HAFTALIK.items()}
    bas = dt.date(2020, 9, 11) if not E["haftalik"] else dt.date.fromisoformat(max(E["haftalik"])) - dt.timedelta(days=60)
    for t, v in g.evds_cek(s, list(HAFTALIK.values()), bas, bugun).items():
        E["haftalik"][t] = {ters[c]: x for c, x in v.items() if c in ters}
    ters = {v: k for k, v in KUR.items()}
    bas = dt.date(2020, 12, 1) if not E["kur"] else dt.date.fromisoformat(max(E["kur"])) - dt.timedelta(days=15)
    for t, v in g.evds_cek(s, list(KUR.values()), bas, bugun).items():
        E["kur"][t] = {ters[c]: x for c, x in v.items() if c in ters}
    log(f"   borçlanma/EVDS: aylık {len(E['aylik'])} dönem (son {max(E['aylik']) if E['aylik'] else '—'}), "
        f"haftalık {len(E['haftalik'])}, kur {len(E['kur'])} gün")


def _bddk_cikti(A, kur):
    """BDDK aylık bülten → {dates, usd (ay sonu kur), g: {grup: {anahtar: [mn TL]}}}"""
    V = (A or {}).get("values") or {}
    donem = sorted(V)
    gunler = sorted(kur)

    def aysonu(p):
        y, m = int(p[:4]), int(p[5:7])
        son = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
        once = [x for x in gunler if x <= son and x[:7] == p]
        return kur[once[-1]].get("usd") if once else None

    gr = {}
    for grup in sorted({k for p in donem for k in V[p]}):
        d = {}
        for ad, tno, rno, kol in BDDK:
            d[ad] = []
            for p in donem:
                h = ((V[p].get(grup) or {}).get(tno) or {}).get(rno)
                d[ad].append(h[kol] if h and len(h) > kol else None)
        gr[grup] = d
    return {"dates": donem, "usd": [aysonu(p) for p in donem], "g": gr,
            "gruplar": [{"key": x["key"], "name": x["name"]} for x in (A or {}).get("groups") or [] if x["key"] in gr]}


def _seri(ham, anahtarlar):
    t = sorted(ham)
    return {"dates": t, "s": {k: [ham[x].get(k) for x in t] for k in anahtarlar}}


def guncelle(g, site, anahtar, log, bddk_aylik=None, kap=True):
    yol = os.path.join(site, "makro", "data", "borclanma.json")
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    try:
        eski = json.load(open(yol, encoding="utf-8"))
    except Exception:
        eski = {}
    E = eski.get("_evds") or {}
    E = {"aylik": E.get("aylik") or {}, "haftalik": E.get("haftalik") or {}, "kur": E.get("kur") or {}}
    K = eski.get("_kap") or {}
    K = {"ham": K.get("ham") or {}, "bas": K.get("bas"), "son": K.get("son")}
    sorun = []
    if anahtar:
        try:
            _evds(g, E, anahtar, log)
        except Exception as e:
            log(f"HATA borçlanma/EVDS: {type(e).__name__}: {e} — önceki veri korunuyor")
            sorun.append("evds")
    else:
        sorun.append("evds")
    if kap:
        try:
            _kap(g, K, log)
        except Exception as e:
            log(f"HATA borçlanma/KAP: {type(e).__name__}: {e} — önceki veri korunuyor")
            sorun.append("kap")
    islem = _kap_cikti(K, E["kur"])
    out = {"updated": g.simdi(), "failed": sorun,
           "bddk": _bddk_cikti(bddk_aylik, E["kur"]),
           "aylik": _seri(E["aylik"], AYLIK), "haftalik": _seri(E["haftalik"], HAFTALIK),
           "kap": islem, "kap_tarama": {"bas": K.get("bas"), "son": K.get("son"), "bekleyen": sum(1 for v in K["ham"].values() if v.get("metin") is None)},
           "kaynak": {"bddk": "https://www.bddk.org.tr/BultenAylik", "evds": "https://evds3.tcmb.gov.tr", "kap": KAP},
           "_evds": E, "_kap": K}
    json.dump(out, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    sen = [x for x in islem if x["tur"] in ("sendikasyon", "murabaha")]
    log(f"   borçlanma: BDDK {len(out['bddk']['dates'])} ay, KAP {len(islem)} işlem ({len(sen)} sendikasyon)"
        + (f", son: {sen[0]['t']} {sen[0]['banka']} {sen[0]['top'] or 0:,.0f} mn $" if sen else ""))
    return sorun
