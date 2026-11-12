import json, os, sys
sys.path.insert(0, "bankacilik")
import guncelle as g, borclanma
A = json.load(open("aylik.json", encoding="utf-8"))
for i in range(2):
    print("== tur", i + 1)
    borclanma.guncelle(g, "site", os.environ.get("EVDS_API_KEY", ""), g.log, A)
j = json.load(open("site/makro/data/borclanma.json", encoding="utf-8"))
for x in j["kap"]:
    print(x["t"], x["banka"], x["tur"], x["top"], "|", x["ozet"][:60], "|", [(d["pb"], d["tutar"], d["gun"], d["maliyet"] and d["maliyet"]["bp"]) for d in x["dilim"]])
