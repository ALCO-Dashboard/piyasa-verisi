import json, re, time, sys, datetime as dt, requests
KAP = "https://www.kap.org.tr"
s = requests.Session(); s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept-Language": "tr"})
U = {}
for sek in ("BANKS", "PAR-BANKS"):
    for x in s.get(f"{KAP}/tr/api/analysis/companies-by-sector/{sek}", headers={"Accept": "application/json"}, timeout=60).json(): U[x["company"].strip()] = x["mkkMemberOid"]
    time.sleep(1)
B = {k: v for k, v in U.items() if "VARLIK YÖNET" not in k}
print(len(B), "banka:", "; ".join(sorted(B)))
def sorgu(oids, bas, bit, mt="IGS", dc="ODA"):
    g = {"fromDate": bas.isoformat(), "toDate": bit.isoformat(), "memberType": mt, "mkkMemberOidList": oids, "inactiveMkkMemberOidList": [], "disclosureClass": dc,
         "subjectList": [], "bdkMemberOidList": [], "mainSector": "", "sector": "", "subSector": "", "market": "", "index": "", "bdkReview": "", "isLate": "", "term": "", "ruleType": "", "period": "", "year": "", "fromSrc": False, "srcCategory": "", "discIndex": []}
    return s.post(KAP + "/tr/api/disclosure/members/byCriteria", json=g, headers={"Accept": "application/json", "Content-Type": "application/json", "Referer": KAP + "/tr/bildirim-sorgu"}, timeout=120)
bugun = dt.date.today()
def say(r, etiket):
    if not (r.ok and r.text[:1] == "["): print(etiket, r.status_code, r.text[:200]); return []
    L = r.json(); c = {}
    for x in L: c[x["kapTitle"]] = c.get(x["kapTitle"], 0) + 1
    print(etiket, "adet", len(L), "sirket", len(c), "|", json.dumps(sorted(c.items(), key=lambda a: -a[1])[:60], ensure_ascii=False)[:1800])
    return L
tum = list(B.values())
for mt in ("IGS", "DDK", "YK", ""):
    say(sorgu(tum, bugun - dt.timedelta(days=60), bugun, mt), f"\n[tum banka 60g mt={mt!r}]"); time.sleep(3)
zr = [v for k, v in B.items() if k.startswith("T.C. ZİRAAT") or k.startswith("KUVEYT")]
for mt in ("IGS", "DDK", "YK", ""):
    for dc in ("ODA", ""):
        say(sorgu(zr, bugun - dt.timedelta(days=360), bugun, mt, dc), f"\n[ziraat+kt 360g mt={mt!r} dc={dc!r}]"); time.sleep(3)
L = say(sorgu(tum, bugun - dt.timedelta(days=365), bugun, "IGS"), "\n[tum banka 365g IGS]")
RE = re.compile(r"sendikasyon|syndicat|murabaha|seküritizasyon|securiti|\bdpr\b|kredi (temin|sözleşme|anlaşma|sağla)|kredi.*temin|yurt ?dışı.*(kredi|finansman)|kaynak temin|finansman temin", re.I)
for x in L:
    if RE.search(x.get("summary") or "") and x["subject"].startswith("Özel Durum"): print("  ", x["publishDate"][:10], x["disclosureIndex"], x["stockCodes"], "|", (x["summary"] or "").strip()[:140])
