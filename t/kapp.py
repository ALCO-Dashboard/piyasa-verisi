import json, re, time, sys, datetime as dt, requests
KAP = "https://www.kap.org.tr"
s = requests.Session(); s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36", "Accept-Language": "tr"})
r = s.get(f"{KAP}/tr/api/analysis/companies-by-sector/BANKS", headers={"Accept": "application/json"}, timeout=60); print("uyeler", r.status_code)
U = r.json(); print(json.dumps(U[:2], ensure_ascii=False)[:600])
oid = [x["mkkMemberOid"] for x in U if "AKBANK" in x["company"]][0]; print("akbank", oid)
time.sleep(2)
bugun = dt.date.today(); bas = bugun - dt.timedelta(days=360)
govde = {"fromDate": bas.isoformat(), "toDate": bugun.isoformat(), "memberType": "IGS", "mkkMemberOidList": [oid], "inactiveMkkMemberOidList": [], "disclosureClass": "ODA",
         "subjectList": [], "bdkMemberOidList": [], "mainSector": "", "sector": "", "subSector": "", "market": "", "index": "", "bdkReview": "", "isLate": "", "term": "", "ruleType": "", "period": "", "year": "", "fromSrc": False, "srcCategory": "", "discIndex": []}
for yol in ["/tr/api/disclosure/members/byCriteria", "/tr/api/memberDisclosureQuery", "/tr/api/disclosures/byCriteria"]:
    try:
        r = s.post(KAP + yol, json=govde, headers={"Accept": "application/json", "Content-Type": "application/json", "Referer": KAP + "/tr/bildirim-sorgu"}, timeout=90)
        print("POST", yol, r.status_code, r.headers.get("content-type"), len(r.content))
        if r.ok and "json" in (r.headers.get("content-type") or ""):
            j = r.json(); L = j if isinstance(j, list) else j.get("data") or j.get("disclosures") or []
            print("  adet", len(L), "anahtarlar", list(L[0].keys()) if L else j if not L else "")
            print("  ornek", json.dumps(L[:2], ensure_ascii=False)[:1500])
            sen = [x for x in L if re.search("sendikasyon|syndicat", json.dumps(x, ensure_ascii=False), re.I)]
            print("  sendikasyon", len(sen)); [print("   ", json.dumps(x, ensure_ascii=False)[:700]) for x in sen[:6]]
            konu = {}
            for x in L: k = str(x.get("subject") or x.get("title") or x.get("kapTitle")); konu[k] = konu.get(k, 0) + 1
            print("  konular", json.dumps(sorted(konu.items(), key=lambda a: -a[1])[:40], ensure_ascii=False))
            if sen:
                did = sen[0].get("disclosureIndex") or sen[0].get("disclosureId") or sen[0].get("id"); time.sleep(3)
                h = s.get(f"{KAP}/tr/Bildirim/{did}", timeout=90); print("  detay", did, h.status_code, len(h.text))
                t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h.text, flags=re.S); t = re.sub(r"<[^>]+>", " ", t); t = re.sub(r"\s+", " ", t)
                i = t.lower().find("sendikasyon"); print("  metin:", t[max(0, i - 1500): i + 2500])
                open("../out/detay.html", "w", encoding="utf-8").write(h.text)
            break
        else: print("  ", r.text[:300])
    except Exception as e: print("  HATA", type(e).__name__, e)
    time.sleep(3)
