import guncelle as g
for tip,a,b in [("EMK","20260302","20260306"),("EMK","20260302","20260320"),("EMK","20260302","20260331"),("EMK","20260302","20260403"),("EMK","20251201","20251205"),("BYF","20260302","20260306"),("YAT","20260302","20260331"),("EMK","20260918","20261007"),("EMK","20260901","20261007")]:
    j=g.tefas("fonGnlBlgSiraliGetir", g.govde_liste(tip,a,b), f"{tip} {a}-{b}")
    print(tip,a,b,len(j["resultList"]),j.get("toplamSayi"),{k:v for k,v in j.items() if k!="resultList"}, flush=True)
