"""Banka Bilanço Verileri: KAP'taki solo finansal raporlardan banka bazında bilanço ve gelir tablosu.

Her banka açıkladığı anda (KAP'taki "Finansal Rapor" bildirimi) yeni dönem eklenir; tüm bankaların açıklaması beklenmez.
Ham tablolar site/bilanco/data/kap_ham.json'da önbellekte tutulur (her rapor bir kez indirilir); sayfanın kullandığı
özet site/bilanco/data/banka.json'a yazılır.

Kullanım: python bilanco/guncelle.py --site site [--yillar 2025 2026]
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dipnot  # noqa: E402
import kap  # noqa: E402

KOK = os.path.dirname(os.path.abspath(__file__))


def log(m):
    print(m, flush=True)


def tablo_sec(T):
    """Rapordaki rolleri ilk satırın XBRL elemanına göre ayır: bilanço (bil), nazım hesaplar (naz), kâr veya zarar tablosu (gel)."""
    out = {}
    for rol, t in T.items():
        k = t.get("kok", "")
        if "bil" not in out and "StatementOfFinancialPosition" in k:
            out["bil"] = t
        elif "naz" not in out and "OffBalanceSheet" in k:
            out["naz"] = t
        elif "gel" not in out and "StatementOfProfitOrLoss" in k and "OtherComprehensive" not in k:
            out["gel"] = t
    return out


# ---------------------------------------------------------------- sayfanın kullandığı kalemler (XBRL elemanı; mevduat / katılım taksonomisi)
BK = [  # anahtar, ad, düzey, elemanlar
    ("nakit", "Nakit Değerler ve Merkez Bankası", 1, ["kap-fr_CashAndCashBalancesAtCentralBanks"]),
    ("bnk", "Bankalar", 1, ["kap-fr_Banks"]),
    ("ppa", "Para Piyasalarından Alacaklar", 1, ["kap-fr_ReceivablesFromMoneyMarkets"]),
    ("mk_gkz", "GUD farkı K/Z'ye yansıtılan fin. varlıklar", 1, ["ifrs-full_FinancialAssetsAtFairValueThroughProfitOrLoss"]),
    ("mk_gdk", "GUD farkı DKG'ye yansıtılan fin. varlıklar", 1, ["ifrs-full_FinancialAssetsAtFairValueThroughOtherComprehensiveIncome"]),
    ("mk_itf", "İtfa edilmiş maliyetle ölçülen menkul değerler", 1, ["kap-fr_FinancialAssetsMeasuredAtAmortisedCost"]),
    ("turev_a", "Türev Finansal Varlıklar", 1, ["ifrs-full_DerivativeFinancialAssets"]),
    ("krd", "Krediler", 1, ["kap-fr_Loans"]),
    ("kir", "Kiralama İşlemlerinden Alacaklar", 1, ["kap-fr_ReceivablesFromLeasingTransactions"]),
    ("bzk", "Beklenen Zarar Karşılıkları (−)", 1, ["kap-fr_AllowanceForExpectedCreditLosses"]),
    ("ortak", "Ortaklık Yatırımları", 1, ["ifrs-full_InvestmentsInSubsidiariesJointVenturesAndAssociates"]),
    ("mdv", "Maddi Duran Varlıklar", 1, ["kap-fr_TangibleAssets"]),
    ("aktif", "VARLIKLAR TOPLAMI", 0, ["ifrs-full_Assets"]),
    ("mev", "Mevduat / Katılım Fonu", 1, ["kap-fr_Deposits", "kap-fr_ParticipationFunds", "kap-fr_FundsCollected"]),
    ("alk", "Alınan Krediler", 1, ["ifrs-full_LoansReceived"]),
    ("ppb", "Para Piyasalarına Borçlar", 1, ["kap-fr_MoneyMarketFunds"]),
    ("imk", "İhraç Edilen Menkul Kıymetler", 1, ["kap-fr_MarketableSecuritiesIssued"]),
    ("turev_p", "Türev Finansal Yükümlülükler", 1, ["kap-fr_DerivativeFinancialLiabilities"]),
    ("sbb", "Sermaye Benzeri Borçlanma Araçları", 1, ["kap-fr_SubordinatedDebt"]),
    ("karsilik", "Karşılıklar", 1, ["ifrs-full_Provisions"]),
    ("dig_p", "Diğer Yükümlülükler", 1, ["ifrs-full_OtherLiabilities"]),
    ("ozk", "Özkaynaklar", 1, ["ifrs-full_Equity"]),
    ("pasif", "YÜKÜMLÜLÜKLER TOPLAMI", 0, ["ifrs-full_EquityAndLiabilities"]),
]
GK = [  # anahtar, mevduat bankası adı, katılım bankası adı, düzey, elemanlar
    ("fg", "Faiz gelirleri", "Kâr payı gelirleri", 0, ["kap-fr_InterestIncome", "kap-fr_ProfitShareIncome"]),
    ("fg_krd", "Kredilerden", "Kredilerden", 1, ["kap-fr_InterestIncomeOnLoans", "kap-fr_ProfitShareOnLoans"]),
    ("fg_zk", "Zorunlu karşılıklardan", "Zorunlu karşılıklardan", 1, ["kap-fr_InterestIncomeOnReserveDeposits", "kap-fr_IncomeReveivedFromReserveDeposits"]),
    ("fg_bnk", "Bankalardan", "Bankalardan", 1, ["kap-fr_InterestIncomeOnBanks", "kap-fr_IncomeReceivedFromBanks"]),
    ("fg_pp", "Para piyasası işlemlerinden", "Para piyasası işlemlerinden", 1, ["kap-fr_InterestIncomeOnMoneyMarketPlacements", "kap-fr_IncomeReceivedFromMoneyMarketPlacement"]),
    ("fg_mk", "Menkul değerlerden", "Menkul değerlerden", 1, ["kap-fr_InterestIncomeOnMarketableSecuritiesPortfolio", "kap-fr_IncomeReceivedFromMarketableSecurities"]),
    ("fg_kir", "Finansal kiralamadan", "Finansal kiralamadan", 1, ["kap-fr_FinanceLeaseIncome"]),
    ("fg_dig", "Diğer", "Diğer", 1, ["kap-fr_OtherInterestIncome", "kap-fr_OtherProfitShareIncome"]),
    ("fd", "Faiz giderleri", "Kâr payı giderleri", 0, ["kap-fr_InterestExpenses", "kap-fr_ProfitShareExpenses"]),
    ("fd_mev", "Mevduata", "Katılma hesaplarına", 1, ["kap-fr_InterestExpensesOnDeposits", "kap-fr_ExpensesOnProfitSharingAccounts"]),
    ("fd_krd", "Kullanılan kredilere", "Kullanılan kredilere", 1, ["kap-fr_InterestExpensesOnFundsBorrowed", "kap-fr_ProfitShareExpenseOnFundsBorrowed"]),
    ("fd_pp", "Para piyasası işlemlerine", "Para piyasası işlemlerine", 1, ["kap-fr_InterestExpensesOnMoneyMarketFunds", "kap-fr_ProfitShareExpenseOnMoneyMarketBorrowing"]),
    ("fd_mk", "İhraç edilen menkul kıymetlere", "İhraç edilen menkul kıymetlere", 1, ["kap-fr_InterestExpensesOnSecuritiesIssued", "kap-fr_ExpenseOnSecuritiesIssued"]),
    ("fd_kir", "Kiralama", "Kiralama", 1, ["kap-fr_LeaseInterestExpenses", "kap-fr_ProfitShareExpenseOnLeases"]),
    ("fd_dig", "Diğer", "Diğer", 1, ["kap-fr_OtherInterestExpense", "kap-fr_OtherProfitShareExpense"]),
    ("nfg", "Net faiz geliri", "Net kâr payı geliri", 0, ["kap-fr_InterestIncomeOrExpense", "kap-fr_ProfitShareIncomeOrExpense"]),
    ("nuk", "Net ücret ve komisyon gelirleri", "Net ücret ve komisyon gelirleri", 0, ["kap-fr_FeeAndCommissionIncomeOrExpenses"]),
    ("tem", "Temettü gelirleri", "Temettü gelirleri", 0, ["kap-fr_DividendIncome"]),
    ("tic", "Ticari kâr / zarar (net)", "Ticari kâr / zarar (net)", 0, ["kap-fr_TradingIncomeOrLoss"]),
    ("tic_sp", "Sermaye piyasası işlemleri", "Sermaye piyasası işlemleri", 1, ["kap-fr_GainsOrLossesArisingFromCapitalMarkets"]),
    ("tic_tur", "Türev finansal işlemler", "Türev finansal işlemler", 1, ["kap-fr_GainsOrLossesArisingFromFinancialTrans"]),
    ("tic_kmb", "Kambiyo işlemleri", "Kambiyo işlemleri", 1, ["kap-fr_ForeignExchangeGainsOrLosses"]),
    ("dfg", "Diğer faaliyet gelirleri", "Diğer faaliyet gelirleri", 0, ["kap-fr_OtherOperatingIncome"]),
    ("fbk", "Faaliyet brüt kârı", "Faaliyet brüt kârı", 0, ["kap-fr_GrossProfitLossFromOperatingActivities"]),
    ("bzk_g", "Beklenen zarar karşılıkları", "Beklenen zarar karşılıkları", 0, ["kap-fr_AllowanceExpensesForExpectedCreditLoss"]),
    ("dkg", "Diğer karşılık giderleri", "Diğer karşılık giderleri", 0, ["kap-fr_OtherAllowanceExpenses"]),
    ("per", "Personel giderleri", "Personel giderleri", 0, ["kap-fr_PersonnelExpenses"]),
    ("dfgd", "Diğer faaliyet giderleri", "Diğer faaliyet giderleri", 0, ["kap-fr_OtherOperatingExpenses"]),
    ("nfk", "Net faaliyet kârı", "Net faaliyet kârı", 0, ["ifrs-full_ProfitLossFromOperatingActivities"]),
    ("ortk", "Özkaynak yöntemi ortaklıklardan", "Özkaynak yöntemi ortaklıklardan", 0, ["ifrs-full_ShareOfProfitLossOfAssociatesAndJoint"]),
    ("vok", "Vergi öncesi kâr", "Vergi öncesi kâr", 0, ["ifrs-full_ProfitLossBeforeTax"]),
    ("ver", "Vergi karşılığı", "Vergi karşılığı", 0, ["ifrs-full_IncomeTaxExpenseContinuingOperation"]),
    ("nk", "DÖNEM NET KÂRI", "DÖNEM NET KÂRI", 0, ["ifrs-full_ProfitLoss"]),
]
NK = [  # nazım hesaplar: anahtar, ad, elemanlar
    ("gnk", "Garanti ve kefaletler (gayrinakdi krediler)", ["kap-fr_GuarantiesAndWarranties", "kap-fr_GuaranteesAndWarranties"]),
    ("taah", "Taahhütler", ["kap-fr_Commitments"]),
    ("vad_al", "Vadeli döviz alım", ["kap-fr_ForwardForeignCurrencyBuyingTransactions"]),
    ("vad_sat", "Vadeli döviz satım", ["kap-fr_ForwardForeignCurrencySaleTransactions"]),
    ("swap_al", "Swap para alım", ["kap-fr_CurrencySwapBuyTransactions", "kap-fr_MoneySwapPurchases"]),
    ("swap_sat", "Swap para satım", ["kap-fr_CurrencySwapSellTransaction", "kap-fr_MoneySwapSales"]),
    ("ops_al", "Para alım opsiyonları", ["kap-fr_CurrencyOptionsBuyTransactions"]),
    ("ops_sat", "Para satım opsiyonları", ["kap-fr_CurrencyOptionsSellTransactions"]),
    ("fut_al", "Futures para alım", ["kap-fr_CurrencyFuturesBuyTransactions"]),
    ("fut_sat", "Futures para satım", ["kap-fr_CurrencyFuturesSellTransactions"]),
]
KAMU = {"ZRT", "VKF", "HLK", "ZKT", "EKT", "VKK"}
PEER = {"QNB", "DNZ", "KT"}
AY_SON = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def bul(satir, elemanlar, kolonlar):
    """Satırlarda elemanı bul (önce tam eşleşme, sonra önek); kolon değerlerini döndür."""
    for tam in (True, False):
        for no, el, lab, v in satir:
            if any(el == e if tam else el.startswith(e) for e in elemanlar):
                return [v.get(k) for k in kolonlar]
    return None


def ozet(H):
    V, donem = {}, {}
    for k, r in H["raporlar"].items():
        d = f"{r['yil']}Q{r['donem']}"
        b = {}
        for key, _, _, els in BK:
            x = bul(r["bil"]["satir"], els, ["4", "5", "6", "7", "8", "9"])
            if x is not None:
                b[key] = [round(y, 1) if y is not None else None for y in x]
        g = {}
        for key, _, _, _, els in GK:
            x = bul(r["gel"]["satir"], els, ["4", "5", "6", "7"])
            if x is not None:
                g[key] = [round(y, 1) if y is not None else None for y in x]
        n = {}
        for key, _, els in NK:
            x = bul((r.get("naz") or {}).get("satir") or [], els, ["4", "5", "6"])
            if x is not None:
                n[key] = [round(y, 1) if y is not None else None for y in x]
        dn = r.get("dipnot") or {}
        bir, vd = dn.get("bireysel") or {}, dn.get("vade") or {}
        x = {"t": r["tarih"], "id": r["id"], "b": b, "g": g, "n": n}
        if bir.get("cari"):
            x["bir"] = [bir["cari"], bir.get("onceki")]
        if vd.get("cari"):
            x["vd"] = [vd["cari"], vd.get("onceki")]
        V.setdefault(d, {})[r["kisa"]] = x
        donem[d] = (r["yil"], r["donem"])
    # 4. çeyrek ve eksik 3 aylık sütunlar: yıllık − 9 aylık
    for d, (y, q) in donem.items():
        for kisa, x in V[d].items():
            for key, v in x["g"].items():
                if v[2] is None or v[3] is None:
                    if q == 1:
                        v[2], v[3] = v[0], v[1]
                    else:
                        p = V.get(f"{y}Q{q - 1}", {}).get(kisa, {}).get("g", {}).get(key)
                        if p and v[0] is not None and p[0] is not None:
                            v[2] = round(v[0] - p[0], 1)
                            v[3] = round(v[1] - p[1], 1) if v[1] is not None and p[1] is not None else None
    sira = sorted(donem, key=lambda d: donem[d], reverse=True)
    D = {
        "updated": H.get("updated"),
        "birim": "milyon TL",
        "bankalar": [{"k": k, "ad": ad, "tur": tur, "kamu": k in KAMU, "peer": k in PEER} for k, ad, tur, _, _ in kap.BANKALAR],
        "donemler": [{"d": d, "ay": donem[d][1] * 3, "son": f"{donem[d][0]}-{AY_SON[donem[d][1]]}", "n": len(V[d])} for d in sira],
        "bk": [[k, ad, lv] for k, ad, lv, _ in BK],
        "gk": [[k, a1, a2, lv] for k, a1, a2, lv, _ in GK],
        "v": {d: V[d] for d in sira},
    }
    return D


def cek(H, a):
    """KAP'taki bildirim listesini al; önbellekte olmayan (ya da düzeltilmiş) solo raporları indir."""
    bugun = dt.date.today()
    yillar = a.yillar or [bugun.year - 1, bugun.year]
    s = kap.oturum()
    U = kap.uyeler(s)
    liste = []
    for sek in ("BANKS", "PAR-BANKS"):
        bs = [(k, unv, U.get((sek, unv))) for k, _, _, unv, sk in kap.BANKALAR if sk == sek]
        eksik = [b[1] for b in bs if not b[2]]
        if eksik:
            log(f"  KAP'ta bulunamadı: {', '.join(eksik)}")
        bs = [b for b in bs if b[2]]
        for i in range(0, len(bs), 10):
            for j in range(0, len(yillar), 2):
                liste += kap.bildirimler(s, sek, bs[i:i + 10], yillar[j:j + 2])
    solo = [x for x in liste if x["nitelik"].lower().startswith("konsolide olmayan")]
    # aynı banka-dönem için birden fazla bildirim (düzeltme) varsa en yenisi
    son = {}
    for x in solo:
        k = f"{x['kisa']}|{x['yil']}|{x['donem']}"
        if k not in son or x["tarih"] > son[k]["tarih"]:
            son[k] = x
    log(f"KAP: {len(liste)} finansal rapor bildirimi, {len(son)} banka-dönem (solo)")
    yeni = 0
    for k, x in sorted(son.items(), key=lambda kv: kv[1]["tarih"], reverse=True):
        eski = H["raporlar"].get(k)
        if eski and eski.get("id") == x["id"]:
            continue
        if yeni >= a.en_fazla:
            break
        try:
            T, ekler = kap.rapor(s, x["id"])
            T = tablo_sec(T)
        except kap.Sinir:
            log("  KAP istek sınırına ulaşıldı; kalan raporlar sonraki çalışmada alınacak")
            break
        except Exception as e:
            log(f"  HATA {k} ({x['id']}): {type(e).__name__}: {e}")
            continue
        if "bil" not in T or "gel" not in T:
            log(f"  {k} ({x['id']}): bilanço / gelir tablosu bulunamadı ({', '.join(T)})")
            continue
        c = kap.BIRIM.get(x["birim"].replace(" ", ""), None)
        if c is None:
            log(f"  {k}: bilinmeyen birim {x['birim']}")
            continue
        r = dict(x)
        r["ekler"] = ekler
        for t in [x for x in ("bil", "naz", "gel") if x in T]:
            r[t] = {"tax": T[t]["tax"], "ad": T[t]["ad"],
                    "satir": [[no, el, lab, {str(kk): round(v * c, 3) for kk, v in vals.items()}] for no, el, lab, vals in T[t]["satir"]]}
        H["raporlar"][k] = r
        yeni += 1
        log(f"  {k}: {x['tarih']} bildirim {x['id']} ({len(r['bil']['satir'])} bilanço, {len(r['gel']['satir'])} gelir satırı)")
    log(f"KAP: {yeni} yeni rapor indirildi")
    dipnotlar(H, s, a)


def dipnotlar(H, s, a):
    """PDF dipnotları (bireysel krediler, mevduat / katılım fonu vade yapısı): en yeni raporlardan başlayarak,
    bir çalışmada en fazla a.pdf_en_fazla PDF; okunamayan PDF iki kez denenir."""
    tur = {k: t for k, _, t, _, _ in kap.BANKALAR}
    bekleyen = [r for r in H["raporlar"].values() if (r.get("dipnot") or {}).get("deneme", 0) < 2 and not (r.get("dipnot") or {}).get("tamam")]
    bekleyen.sort(key=lambda r: (r["yil"], r["donem"], r["tarih"]), reverse=True)
    n = 0
    for r in bekleyen:
        if n >= a.pdf_en_fazla:
            break
        k = f"{r['kisa']}|{r['yil']}|{r['donem']}"
        d = r.setdefault("dipnot", {})
        try:
            if not r.get("ekler"):
                _, r["ekler"] = kap.rapor(s, r["id"])
            ek = kap.pdf_ek(r["ekler"])
            if not ek:
                d.update(deneme=9, hata="PDF eki yok")
                continue
            n += 1
            sonuc = dipnot.oku(kap.dosya(s, ek[0]), tur.get(r["kisa"]) == "katilim", f"{r['kisa']}_{r['yil']}_{r['donem']}")
        except kap.Sinir:
            log("  KAP istek sınırına ulaşıldı (PDF); kalanlar sonraki çalışmada")
            break
        except Exception as e:
            d["deneme"] = d.get("deneme", 0) + 1
            d["hata"] = f"{type(e).__name__}: {e}"[:200]
            log(f"  {k} PDF okunamadı: {d['hata']}")
            continue
        d.update(sonuc, ek=ek[0], deneme=d.get("deneme", 0) + 1)
        d["tamam"] = bool(sonuc.get("bireysel") and sonuc.get("vade"))
        log(f"  {k} dipnot: bireysel {'✓' if sonuc.get('bireysel') else '—'}, vade {'✓' if sonuc.get('vade') else '—'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site")
    ap.add_argument("--yillar", nargs="*", type=int)
    ap.add_argument("--en-fazla", type=int, default=40, help="bir çalışmada indirilecek en fazla rapor")
    ap.add_argument("--pdf-en-fazla", type=int, default=12, help="bir çalışmada okunacak en fazla PDF")
    ap.add_argument("--yalniz-ozet", action="store_true", help="KAP'a gitmeden önbellekten banka.json üret")
    a = ap.parse_args()
    cikti = os.path.join(a.site, "bilanco")
    os.makedirs(os.path.join(cikti, "data"), exist_ok=True)
    yol = os.path.join(cikti, "data", "kap_ham.json")
    try:
        H = json.load(open(yol, encoding="utf-8"))
    except Exception:
        H = {"raporlar": {}}
    if not H["raporlar"] and os.path.exists(os.path.join(KOK, "tohum.json.gz")):   # ilk kurulum: önceden indirilmiş raporlar
        import gzip
        H = json.load(gzip.open(os.path.join(KOK, "tohum.json.gz"), "rt", encoding="utf-8"))
        log(f"  tohum dosyasından {len(H['raporlar'])} rapor yüklendi")
    if a.yalniz_ozet:
        return yaz(a.site, H)
    try:
        cek(H, a)
    except Exception as e:                       # KAP'a ulaşılamazsa önbellekteki verilerle sayfa yine üretilir
        log(f"  HATA KAP: {type(e).__name__}: {e}")
    H["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump(H, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    log(f"Banka bilanço: önbellekte {len(H['raporlar'])} rapor")
    yaz(a.site, H)


def yaz(site, H):
    cikti = os.path.join(site, "bilanco")
    os.makedirs(os.path.join(cikti, "data"), exist_ok=True)
    D = ozet(H)
    json.dump(D, open(os.path.join(cikti, "data", "banka.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(cikti, "index.html"), "w", encoding="utf-8").write(open(os.path.join(KOK, "sayfa.html"), encoding="utf-8").read())
    if D["donemler"]:
        son = D["donemler"][0]
        log(f"Özet: {len(D['donemler'])} dönem; son dönem {son['d']} ({son['n']} banka)")
        try:
            sys.path.insert(0, os.path.join(KOK, "..", "ortak"))
            from durum import yaz as dyaz
            dyaz(site, "bilanco", max(x["t"] for x in D["v"][son["d"]].values())[:10])
        except Exception as e:
            log(f"durum.json yazılamadı: {e}")


if __name__ == "__main__":
    main()
