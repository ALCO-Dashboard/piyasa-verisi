"""KAP'tan bankaların BDDK formatındaki solo (konsolide olmayan) finansal tablolarını çeker.

Akış
  1) /api/analysis/companies-by-sector/{BANKS|PAR-BANKS}: banka adı → mkkMemberOid
  2) /api/export/compareItems (Excel): her banka, yıl ve dönem için finansal rapor bildirim numarası, yayın tarihi,
     niteliği (Konsolide / Konsolide Olmayan) ve sunum birimi (1000TL, 1000000TL …)
  3) /tr/Bildirim/{id}: bildirim sayfasındaki XBRL tabloları (bilanço, nazım hesaplar, kâr veya zarar tablosu …)
     satır satır okunur. Her banka-dönem raporu bir kez indirilir; sonuçlar önbellekte tutulur.
İstekler aralıklı gönderilir (KAP'a yük bindirmemek için).
"""
import datetime as dt
import html as htmlmod
import io
import re
import time

import requests

KAP = "https://www.kap.org.tr"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
BEKLE = 2.5          # sayfa istekleri arası saniye

# kısa kod, ad, tür, KAP'taki unvan (büyük harf), KAP sektörü
BANKALAR = [
    ("ZRT", "Ziraat Bankası", "mevduat", "T.C. ZİRAAT BANKASI A.Ş.", "BANKS"),
    ("ISB", "İş Bankası", "mevduat", "TÜRKİYE İŞ BANKASI A.Ş.", "BANKS"),
    ("GAR", "Garanti BBVA", "mevduat", "TÜRKİYE GARANTİ BANKASI A.Ş.", "BANKS"),
    ("VKF", "Vakıfbank", "mevduat", "TÜRKİYE VAKIFLAR BANKASI T.A.O.", "BANKS"),
    ("HLK", "Halkbank", "mevduat", "TÜRKİYE HALK BANKASI A.Ş.", "BANKS"),
    ("YK", "Yapı Kredi", "mevduat", "YAPI VE KREDİ BANKASI A.Ş.", "BANKS"),
    ("AKB", "Akbank", "mevduat", "AKBANK T.A.Ş.", "BANKS"),
    ("QNB", "QNB Finansbank", "mevduat", "QNB BANK A.Ş.", "BANKS"),
    ("DNZ", "Denizbank", "mevduat", "DENİZBANK A.Ş.", "BANKS"),
    ("TEB", "TEB", "mevduat", "TÜRK EKONOMİ BANKASI A.Ş.", "BANKS"),
    ("ING", "ING Bank", "mevduat", "ING BANK A.Ş.", "BANKS"),
    ("FBA", "Fibabanka", "mevduat", "FİBABANKA A.Ş.", "BANKS"),
    ("SKR", "Şekerbank", "mevduat", "ŞEKERBANK T.A.Ş.", "BANKS"),
    ("ENP", "Enpara", "mevduat", "ENPARA BANK A.Ş.", "BANKS"),
    ("KT", "Kuveyt Türk", "katilim", "KUVEYT TÜRK KATILIM BANKASI A.Ş.", "PAR-BANKS"),
    ("VKK", "Vakıf Katılım", "katilim", "VAKIF KATILIM BANKASI A.Ş.", "PAR-BANKS"),
    ("ZKT", "Ziraat Katılım", "katilim", "ZİRAAT KATILIM BANKASI A.Ş.", "PAR-BANKS"),
    ("TF", "Türkiye Finans", "katilim", "TÜRKİYE FİNANS KATILIM BANKASI A.Ş.", "PAR-BANKS"),
    ("EKT", "Emlak Katılım", "katilim", "TÜRKİYE EMLAK KATILIM BANKASI A.Ş.", "PAR-BANKS"),
    ("ALB", "Albaraka Türk", "katilim", "ALBARAKA TÜRK KATILIM BANKASI A.Ş.", "PAR-BANKS"),
    ("DNY", "Dünya Katılım", "katilim", "DÜNYA KATILIM BANKASI A.Ş.", "PAR-BANKS"),
    ("HYT", "Hayat Finans", "katilim", "HAYAT FİNANS KATILIM BANKASI A.Ş.", "PAR-BANKS"),
    ("TOM", "T.O.M. Katılım", "katilim", "T.O.M. KATILIM BANKASI A.Ş.", "PAR-BANKS"),
]
BIRIM = {"TL": 1e-6, "1000TL": 1e-3, "1000000TL": 1.0, "1000000000TL": 1e3}   # → milyon TL


def log(m):
    print(m, flush=True)


def oturum():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "tr"})
    return s


def uyeler(s):
    """{(sektör, unvan): oid}"""
    out = {}
    for sek in ("BANKS", "PAR-BANKS"):
        r = s.get(f"{KAP}/tr/api/analysis/companies-by-sector/{sek}", headers={"Accept": "application/json"}, timeout=60)
        r.raise_for_status()
        for x in r.json():
            out[(sek, x["company"].strip())] = x["mkkMemberOid"]
        time.sleep(1)
    return out


_KALEM = {}


def kalem_id(s, sek, etiket="Varlıklar Toplamı"):
    if sek in _KALEM:
        return _KALEM[sek]
    r = s.get(f"{KAP}/tr/api/analysis/compare-items-by-sector/{sek}", headers={"Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    _KALEM[sek] = next((x["itemId"] for x in r.json() if x["websiteLabel"].strip().lower() == etiket.lower()), r.json()[0]["itemId"])
    return _KALEM[sek]


def bildirimler(s, sek, banka, yillar):
    """banka: [(kısa, unvan, oid)] (en fazla 10). → [{kisa, id, tarih, yil, donem, nitelik, birim}]"""
    import openpyxl
    body = {"companyType": sek, "mkkMemberIdList": [b[2] for b in banka], "mkkMemberTitleList": [b[1] for b in banka],
            "yearList": [str(y) for y in yillar], "periodList": ["1", "2", "3", "4"], "itemIdList": [kalem_id(s, sek)], "sectors": [sek]}
    time.sleep(1)
    r = s.post(f"{KAP}/tr/api/export/compareItems", json=body, headers={"Content-Type": "application/json"}, timeout=120)
    r.raise_for_status()
    ws = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True).worksheets[0]
    unvan = {b[1]: b[0] for b in banka}
    out, bas = [], None
    for row in ws.iter_rows(values_only=True):
        if row and row[0] == "Şirket":
            bas = row
            continue
        if not bas or not row or not row[0] or not row[1]:
            continue
        k = unvan.get(str(row[0]).strip())
        if not k:
            continue
        t = dt.datetime.strptime(str(row[2]).strip(), "%d-%m-%Y %H:%M:%S")
        out.append({"kisa": k, "id": str(row[1]).strip(), "tarih": t.strftime("%Y-%m-%d %H:%M"), "yil": int(row[3]), "donem": int(row[4]),
                    "nitelik": str(row[5]).strip(), "birim": str(row[6]).strip()})
    return out


def tablo_oku(sayfa):
    """Bildirim sayfasındaki XBRL satırları → {rol: {"ad": tablo adı, "satir": [[satır no, eleman, etiket, {kolon: değer}], …]}}"""
    out = {}
    for ch in re.split(r'<tr class="(?=[a-z-]+_role_\d+-row-\d+)', sayfa)[1:]:
        m = re.match(r"([a-z-]+)_role_(\d+)-row-(\d+)", ch)
        if not m:
            continue
        rol, no = m.group(2), int(m.group(3))
        T = out.setdefault(rol, {"tax": m.group(1), "ad": "", "satir": {}})
        if no in T["satir"]:
            continue
        el = re.search(r'class="gwt-Label taxonomy-field-name">([^<|]*)', ch)
        lab = re.search(r'content-tr" style="display:block">([^<]*)<', ch)
        vals = {}
        for a, b in re.findall(r'col-order-class-(\d+)"><div><div class="[^"]*" title="([^"]*)"', ch):
            try:
                vals[int(a)] = float(b.replace(",", "."))
            except ValueError:
                pass
        T["satir"][no] = [no, el.group(1) if el else "", htmlmod.unescape(lab.group(1)).strip() if lab else "", vals]
    for T in out.values():
        T["satir"] = [T["satir"][k] for k in sorted(T["satir"])]
        T["ad"] = next((x[2] for x in T["satir"] if x[2]), "")
        T["kok"] = T["satir"][0][1] if T["satir"] else ""
    return out


class Sinir(Exception):
    """KAP istek sınırı (HTTP 429): bu çalışmada daha fazla rapor istenmez."""


def rapor(s, bid):
    for deneme in range(3):
        time.sleep(BEKLE if deneme == 0 else 60 * deneme)
        r = s.get(f"{KAP}/tr/Bildirim/{bid}", timeout=120)
        if r.status_code == 429:
            log(f"  KAP istek sınırı (429), {60 * (deneme + 1)} sn bekleniyor")
            continue
        r.raise_for_status()
        return tablo_oku(r.text)
    raise Sinir()
