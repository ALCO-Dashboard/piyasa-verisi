import json, re, time, sys, datetime as dt, requests
KAP = "https://www.kap.org.tr"
s = requests.Session(); s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept-Language": "tr"})
U = {}
for sek in ("BANKS", "PAR-BANKS"):
    for x in s.get(f"{KAP}/tr/api/analysis/companies-by-sector/{sek}", headers={"Accept": "application/json"}, timeout=60).json(): U[x["company"].strip()] = x["mkkMemberOid"]
    time.sleep(1)
print(len(U), "uye:", "; ".join(sorted(U)))
def sorgu(oid, bas, bit):
    g = {"fromDate": bas.isoformat(), "toDate": bit.isoformat(), "memberType": "IGS", "mkkMemberOidList": [oid], "inactiveMkkMemberOidList": [], "disclosureClass": "ODA",
         "subjectList": [], "bdkMemberOidList": [], "mainSector": "", "sector": "", "subSector": "", "market": "", "index": "", "bdkReview": "", "isLate": "", "term": "", "ruleType": "", "period": "", "year": "", "fromSrc": False, "srcCategory": "", "discIndex": []}
    r = s.post(KAP + "/tr/api/disclosure/members/byCriteria", json=g, headers={"Accept": "application/json", "Content-Type": "application/json", "Referer": KAP + "/tr/bildirim-sorgu"}, timeout=90)
    return r
bugun = dt.date.today()
# tarih araligi siniri
for gun in (1100, 2500):
    r = sorgu(U["AKBANK T.A.Ş."], bugun - dt.timedelta(days=gun), bugun); print("aralik", gun, r.status_code, len(r.content), (len(r.json()) if r.ok and r.text[:1] == "[" else r.text[:200])); time.sleep(3)
ADLAR = ["AKBANK T.A.Ş.", "TÜRKİYE GARANTİ BANKASI A.Ş.", "TÜRKİYE İŞ BANKASI A.Ş.", "YAPI VE KREDİ BANKASI A.Ş.", "TÜRKİYE VAKIFLAR BANKASI T.A.O.", "T.C. ZİRAAT BANKASI A.Ş.", "TÜRKİYE HALK BANKASI A.Ş.", "QNB BANK A.Ş.", "DENİZBANK A.Ş.", "TÜRK EKONOMİ BANKASI A.Ş.",
         "KUVEYT TÜRK KATILIM BANKASI A.Ş.", "ALBARAKA TÜRK KATILIM BANKASI A.Ş.", "TÜRKİYE FİNANS KATILIM BANKASI A.Ş.", "VAKIF KATILIM BANKASI A.Ş.", "ZİRAAT KATILIM BANKASI A.Ş.", "TÜRKİYE SINAİ KALKINMA BANKASI A.Ş.", "TÜRKİYE İHRACAT KREDİ BANKASI A.Ş."]
RE = re.compile(r"sendikasyon|syndicat|murabaha|seküritizasyon|securiti|dpr|yurt ?dışı.*kredi|kredi.*yurt ?dışı|sürdürülebilir.*kredi|kredi temin|kredi sağlan|borçlanma", re.I)
bul = []
for ad in ADLAR:
    if ad not in U: print("YOK", ad); continue
    r = sorgu(U[ad], bugun - dt.timedelta(days=720), bugun); time.sleep(2.5)
    if not r.ok: print(ad, r.status_code); continue
    L = r.json(); ozet = {}
    for x in L:
        if x["subject"].startswith("Özel Durum"): ozet[x["summary"] or ""] = ozet.get(x["summary"] or "", 0) + 1
    hit = [x for x in L if RE.search((x.get("summary") or ""))]
    print(f"\n== {ad}: {len(L)} bildirim; eşleşen {len(hit)}")
    for x in hit: print("  ", x["publishDate"], x["disclosureIndex"], "|", x["subject"][:40], "|", x["summary"])
    print("   diğer ÖDA özetleri:", json.dumps(sorted(ozet.items(), key=lambda a: -a[1])[:25], ensure_ascii=False)[:1500])
    bul += [(ad, x) for x in hit if re.search("sendikasyon|syndicat|murabaha", x["summary"] or "", re.I)][:2]
print("\n\n######## DETAYLAR")
for ad, x in bul[:16]:
    time.sleep(3); h = s.get(f"{KAP}/tr/Bildirim/{x['disclosureIndex']}", timeout=90)
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h.text, flags=re.S); t = re.sub(r"<[^>]+>", " ", t); t = re.sub(r"&nbsp;", " ", t); t = re.sub(r"\s+", " ", t)
    i = t.find("oda_ExplanationSection"); i = i if i >= 0 else t.find("Açıklamalar")
    print(f"\n--- {ad} {x['publishDate']} {x['disclosureIndex']} ({h.status_code}, {len(h.text)})\n", t[i:i + 2200])
    if x is bul[0][1]: open("../out/detay.html", "w", encoding="utf-8").write(h.text)
