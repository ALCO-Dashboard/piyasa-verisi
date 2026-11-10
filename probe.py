import sys, json
sys.path.insert(0, "bankacilik")
import guncelle as g, swap
swap.EN_FAZLA = 6
swap.guncelle(g, "out", "", print)
d = json.load(open("out/makro/data/swap.json"))
print(json.dumps(d["seri"], ensure_ascii=False))
# 2. çalışma: yalnız tazeleme
swap.EN_FAZLA = 2
swap.guncelle(g, "out", "", print)
