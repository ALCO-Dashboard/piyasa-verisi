"""Fon Detay — günlük veri güncelleme.

Her çalıştığında:
  1) site/store.enc varsa şifresini çözer (önceki günlerin verisi), yoksa sıfırdan başlar
  2) TEFAS'tan eksik günleri ve son 3 iş gününü çeker (yatırım, emeklilik, borsa yatırım fonları)
  3) TCMB döviz alış kurlarını ve altın/gümüş fiyatını tamamlar
  4) Sayfanın okuduğu veriyi hazırlar, şifreler ve site/ klasörüne yazar

Şifre SITE_PASSWORD ortam değişkeninden okunur.
"""
import datetime as dt
import gzip
import json
import os
import re
import statistics
import sys
import time

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

BASLANGIC = "2025-12-01"          # verinin tutulduğu ilk gün (31.12.2025'ten bir ay öncesi, 1 aylık getiri için)
TIPLER = ("YAT", "EMK", "BYF")
PARCA = {"YAT": 8, "EMK": 20, "BYF": 20}   # tek sorguda kaç iş günü (TEFAS ~1 aydan uzun aralıkta boş döner)
API = "https://www.tefas.gov.tr/api/funds/"
BASLIK = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Origin": "https://www.tefas.gov.tr",
    "Referer": "https://www.tefas.gov.tr/tr/fon-verileri",
}
SITE = "site"
OTURUM = requests.Session()


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- şifreleme
def _anahtar(sifre: str, tuz: bytes) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=tuz, iterations=200_000).derive(sifre.encode("utf-8"))


def sifrele(nesne, sifre: str) -> bytes:
    ham = gzip.compress(json.dumps(nesne, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)
    tuz, nonce = os.urandom(16), os.urandom(12)
    return b"FD1" + tuz + nonce + AESGCM(_anahtar(sifre, tuz)).encrypt(nonce, ham, None)


def coz(veri: bytes, sifre: str):
    if veri[:3] != b"FD1":
        raise ValueError("dosya biçimi tanınmadı")
    ham = AESGCM(_anahtar(sifre, veri[3:19])).decrypt(veri[19:31], veri[31:], None)
    return json.loads(gzip.decompress(ham))


# ---------------------------------------------------------------- TEFAS
def tefas(uc: str, govde: dict, etiket: str):
    """Tek bir TEFAS sorgusu. Sınır aşımında bekleyip yeniden dener."""
    for deneme in range(12):
        try:
            r = OTURUM.post(API + uc, json=govde, headers=BASLIK, timeout=90)
            j = r.json()
        except Exception as e:  # ağ hatası ya da JSON olmayan yanıt
            log(f"   {etiket}: hata ({type(e).__name__}), yeniden denenecek")
            time.sleep(15 + 5 * deneme)
            continue
        if isinstance(j, dict) and j.get("resultList") is not None:
            time.sleep(2.5)
            return j
        if isinstance(j, dict) and j.get("faultCode"):      # ERR-224: sorgu sınırı
            time.sleep(20 + 5 * deneme)
            continue
        if isinstance(j, dict) and "resultList" in j:        # veri yok (tatil vb.)
            time.sleep(2.5)
            return {"resultList": [], "toplamSayi": 0}
        log(f"   {etiket}: beklenmeyen yanıt {str(j)[:160]}")
        time.sleep(15)
    raise RuntimeError(f"TEFAS yanıt vermedi: {etiket}")


def govde_liste(tip, a, b, bas=1, bit=60000):
    return {"fonTipi": tip, "fonKodu": None, "aramaMetni": None, "fonTurKod": None, "fonGrubu": None,
            "sfonTurKod": None, "basTarih": a, "bitTarih": b, "basSira": bas, "bitSira": bit,
            "fonTurAciklama": None, "dil": "TR", "kurucuKod": None, "sira": None, "yon": None,
            "sFonTurKod": "", "fonKod": None, "fonGrup": "", "fonUnvanTip": ""}


def govde_temel(tip):
    return {"dil": "TR", "fonTipi": tip, "kurucuKodu": None, "fonTurKod": None, "fonGrubu": None,
            "fonTurAciklama": None, "islem": None, "sfonTurKod": None}


def sayfali(uc, tip, a, b, etiket):
    """Liste uç noktasını, toplam satır sayısına ulaşana kadar sayfa sayfa çeker."""
    hepsi, bas, adim = [], 1, 60000
    while True:
        j = tefas(uc, govde_liste(tip, a, b, bas, bas + adim - 1), etiket)
        satir = j["resultList"]
        hepsi += satir
        toplam = j.get("toplamSayi") or len(hepsi)
        if not satir or len(hepsi) >= toplam:
            return hepsi
        bas += adim


def is_gunleri(a: dt.date, b: dt.date):
    g, out = a, []
    while g <= b:
        if g.weekday() < 5:
            out.append(g.isoformat())
        g += dt.timedelta(days=1)
    return out


def kisa(d: str) -> str:
    return d.replace("-", "")


# ---------------------------------------------------------------- depo
def bos_depo():
    return {"dates": [], "sets": {t: {"name": {}, "v": {}, "p": {}, "k": {}} for t in TIPLER},
            "info": {t: {} for t in TIPLER}, "pd": {t: {} for t in TIPLER}, "tcmb": {}, "oz": {}}


def tarih_ekle(depo, d):
    if d in depo["dates"]:
        return
    depo["dates"].append(d)
    depo["dates"].sort()
    i = depo["dates"].index(d)
    for t in TIPLER:
        for alan in ("v", "p", "k"):
            for dizi in depo["sets"][t][alan].values():
                dizi.insert(i, 0)


def tarih_sil(depo, d):
    i = depo["dates"].index(d)
    depo["dates"].pop(i)
    for t in TIPLER:
        for alan in ("v", "p", "k"):
            for dizi in depo["sets"][t][alan].values():
                dizi.pop(i)


def gunleri_yaz(depo, tip, gunler, satirlar):
    """Verilen günlerin değerlerini sıfırlayıp gelen satırlarla doldurur."""
    S = depo["sets"][tip]
    for d in gunler:
        tarih_ekle(depo, d)
    n = len(depo["dates"])
    ix = {d: depo["dates"].index(d) for d in gunler}
    for alan in ("v", "p", "k"):
        for dizi in S[alan].values():
            for i in ix.values():
                dizi[i] = 0
    for x in satirlar:
        d, kod = x.get("tarih"), x.get("fonKodu")
        pb, fiyat = x.get("portfoyBuyukluk") or 0, x.get("fiyat") or 0
        if d not in ix or not kod or pb <= 0 or fiyat <= 0:
            continue
        if kod not in S["v"]:
            S["v"][kod], S["p"][kod], S["k"][kod] = [0] * n, [0] * n, [0] * n
        S["name"][kod] = x.get("fonUnvan") or S["name"].get(kod, kod)
        i = ix[d]
        S["v"][kod][i] = round(pb / 1000)                       # bin TL
        S["p"][kod][i] = float(f"{fiyat:.7g}")
        S["k"][kod][i] = int(x.get("kisiSayisi") or 0)


def gun_sayisi(depo, tip, d):
    i = depo["dates"].index(d)
    return sum(1 for dizi in depo["sets"][tip]["v"].values() if dizi[i])


# ---------------------------------------------------------------- kurlar
def tcmb_cek(depo, bugun: dt.date):
    """Eksik TCMB bültenlerini indirir (döviz alış). Tatil günlerinde bülten yoktur."""
    ilk = dt.date.fromisoformat(BASLANGIC) - dt.timedelta(days=10)
    eksik = [d for d in is_gunleri(ilk, bugun) if d not in depo["tcmb"] and d not in depo.get("tcmb_yok", [])]
    yok = set(depo.get("tcmb_yok", []))
    for d in eksik:
        y, m, g = d.split("-")
        try:
            r = OTURUM.get(f"https://www.tcmb.gov.tr/kurlar/{y}{m}/{g}{m}{y}.xml", headers={"User-Agent": BASLIK["User-Agent"]}, timeout=40)
        except Exception as e:
            log(f"   TCMB {d}: hata {type(e).__name__}")
            continue
        if r.status_code != 200:
            if dt.date.fromisoformat(d) < bugun - dt.timedelta(days=3):
                yok.add(d)                                       # tatil: bir daha sorma
            continue
        kur = []
        for kod in ("USD", "EUR", "GBP"):
            mm = re.search(r'CurrencyCode="%s".*?<ForexBuying>([0-9.]+)<' % kod, r.text, re.S)
            kur.append(float(mm.group(1)) if mm else None)
        if all(kur):
            depo["tcmb"][d] = kur
        time.sleep(0.15)
    depo["tcmb_yok"] = sorted(yok)
    log(f"TCMB: {len(depo['tcmb'])} bülten (son: {max(depo['tcmb']) if depo['tcmb'] else '-'})")


def metal_cek(depo):
    """Altın ve gümüş ons fiyatı (USD). Kaynak yanıt vermezse fon fiyatlarından türetilir."""
    if os.path.exists("metal_seed.json"):
        for d, v in json.load(open("metal_seed.json", encoding="utf-8")).items():
            depo["oz"].setdefault(d, v)
    seri = {}
    for ad, sembol in (("xau", "xauusd"), ("xag", "xagusd")):
        try:
            r = OTURUM.get(f"https://stooq.com/q/d/l/?s={sembol}&i=d", headers={"User-Agent": BASLIK["User-Agent"]}, timeout=40)
            satirlar = [s.split(",") for s in r.text.strip().splitlines()[1:]]
            seri[ad] = {s[0]: float(s[4]) for s in satirlar if len(s) >= 5 and s[0] >= "2025-11-15"}
        except Exception as e:
            log(f"   Metal fiyatı ({ad}) alınamadı: {type(e).__name__}")
            seri[ad] = {}
    yeni = 0
    for d in sorted(set(seri["xau"]) & set(seri["xag"])):
        if d not in depo["oz"]:
            depo["oz"][d] = [seri["xau"][d], seri["xag"][d]]
            yeni += 1
    log(f"Metal: {len(depo['oz'])} gün (son: {max(depo['oz']) if depo['oz'] else '-'}, yeni: {yeni})")


# ---------------------------------------------------------------- sınıflama
RENK = {
    "YAT": {"Para Piyasası": "#2563eb", "Döviz": "#0d9488", "Serbest-RiskY": "#7c3aed", "Hisse": "#d97706",
            "Borçlanma Araçları": "#059669", "Altın": "#dc2626", "Serbest-RiskD": "#0891b2", "Değişken": "#db2777",
            "Fon Sepeti": "#64748b", "Gümüş": "#84cc16", "Arbitraj": "#f97316"},
    "EMK": {"Altın": "#dc2626", "Para Piyasası": "#2563eb", "Katkı": "#0d9488", "Değişken": "#db2777",
            "Hisse": "#d97706", "Borçlanma Araçları": "#059669", "Standart Emeklilik": "#7c3aed",
            "Fon Sepeti": "#64748b", "Karma": "#0891b2", "Başlangıç": "#f97316", "Gümüş": "#84cc16", "Diğer": "#94a3b8"},
    "BYF": {"Hisse": "#d97706", "Para Piyasası (TLREF)": "#2563eb", "Altın": "#dc2626", "Gümüş": "#84cc16",
            "Döviz / Yabancı": "#0d9488", "Borçlanma Araçları": "#059669", "Diğer": "#64748b"},
}
ALTIN = re.compile(r"(?<![A-ZÇĞİÖŞÜ])ALTIN(?![A-ZÇĞİÖŞÜ])")
ETIKET = {
    "hs": "Hisse Senedi", "dt": "Devlet Tahvili", "kibd": "Döviz Cinsi Kamu İç Borçlanma Araçları", "fb": "Finansman Bonosu",
    "ost": "Özel Sektör Tahvili", "kba": "Kamu Dış Borçlanma Araçları", "osdb": "Özel Sektör Dış Borçlanma Araçları",
    "kkstl": "Kamu Kira Sertifikaları (TL)", "osks": "Özel Sektör Kira Sertifikaları", "oksyd": "Özel Sektör Yurt Dışı Kira Sertifikaları",
    "tr": "Ters-Repo", "btas": "BİST Taahhütlü İşlem Pazarı Satım", "tpp": "Takasbank Para Piyasası", "vmd": "Mevduat (Döviz)",
    "vmtl": "Mevduat (TL)", "khd": "Katılma Hesabı (Döviz)", "khtl": "Katılma Hesabı (TL)", "yhs": "Yabancı Hisse Senedi",
    "ybkb": "Yabancı Kamu Borçlanma Araçları", "ybosb": "Yabancı Özel Sektör Borçlanma Araçları",
    "byf": "Borsa Yatırım Fonları Katılma Payları", "gykb": "Gayrimenkul Yatırım Fonları Katılma Payları",
    "gsykb": "Girişim Sermayesi Yatırım Fonları Katılma Payları", "yyf": "Yatırım Fonları Katılma Payları",
    "vint": "Vadeli İşlemler Nakit Teminatları", "hb": "Hazine Bonosu", "bb": "Banka Bonosu", "db": "Döviz Ödemeli Bono",
    "dot": "Döviz Ödemeli Tahvil", "eut": "Eurobond", "vdm": "Varlığa Dayalı Menkul Kıymetler", "kks": "Kamu Kira Sertifikaları",
    "kksd": "Kamu Kira Sertifikaları (Döviz)", "kksyd": "Kamu Yurt Dışı Kira Sertifikaları", "vm": "Vadeli Mevduat",
    "vmau": "Mevduat (Altın)", "kh": "Katılma Hesabı", "khau": "Katılma Hesabı (Altın)", "r": "Repo",
    "btaa": "BİST Taahhütlü İşlem Pazarı Alım", "km": "Kıymetli Madenler", "kmbyf": "Kıymetli Maden Borsa Yatırım Fonları",
    "kmkba": "Kıymetli Maden Cinsinden Kamu Borçlanma Araçları", "kmkks": "Kıymetli Maden Cinsinden Kamu Kira Sertifikaları",
    "ymk": "Yabancı Menkul Kıymetler", "yba": "Yabancı Borçlanma Araçları", "ybyf": "Yabancı Borsa Yatırım Fonları",
    "fkb": "Fon Katılma Belgesi", "t": "Türev Araçları", "gas": "Gayrimenkul Sertifikası", "gyy": "Gayrimenkul Yatırımları",
    "gsyy": "Girişim Sermayesi Yatırımları", "d": "Diğer", "bpp": "Borsa Para Piyasası",
}
PD_ATLA = {"fonKodu", "fonUnvan", "tarih", "bilFiyat"}


def ucret(a, b):
    def oku(s):
        try:
            return float(str(s).rstrip(",").replace(",", "."))
        except Exception:
            return None
    a, b = oku(a), oku(b)
    return a if a else (b if b else a)


def oynaklik(fiyat, kur):
    """Fon fiyatının verilen kura bölünmüş günlük getirilerinin standart sapması."""
    s = [(i, fiyat[i] / kur[i]) for i in range(len(fiyat)) if fiyat[i] and kur[i]]
    r = [s[i][1] / s[i - 1][1] - 1 for i in range(1, len(s)) if s[i][0] == s[i - 1][0] + 1]
    r = [x for x in r if abs(x) < 0.2]
    return statistics.pstdev(r) if len(r) > 20 else None


def yat_kural(ad, tur, birim, risk):
    if birim == "XAU":
        return "Altın"
    if birim == "XAG":
        return "Gümüş"
    if birim in ("USD", "EUR", "GBP"):
        return "Döviz"
    if "ARBİTRAJ" in ad:
        return "Arbitraj"
    if "HİSSE" in ad:
        return "Hisse"
    if "FON SEPETİ" in ad:
        return "Fon Sepeti"
    if "BORÇLANMA" in ad or "KİRA SERTİFİKA" in ad:
        return "Borçlanma Araçları"
    if "SERBEST" in ad or "Serbest" in (tur or ""):
        return "Serbest-RiskD" if risk in (1, 2) else "Serbest-RiskY"
    return "Değişken"


def emk_kural(ad):
    for anahtar, kat in (("GÜMÜŞ", "Gümüş"), ("PARA PİYASASI", "Para Piyasası"), ("KATKI", "Katkı"),
                         ("BAŞLANGIÇ", "Başlangıç"), ("STANDART", "Standart Emeklilik"), ("HİSSE", "Hisse"),
                         ("FON SEPETİ", "Fon Sepeti"), ("BORÇLANMA", "Borçlanma Araçları"),
                         ("KİRA SERT", "Borçlanma Araçları"), ("KARMA", "Karma"), ("DEĞİŞKEN", "Değişken")):
        if anahtar in ad:
            return kat
    return "Altın" if ALTIN.search(ad) or "KIYMETLİ MADEN" in ad else "Diğer"


def byf_kural(ad):
    if "GÜMÜŞ" in ad:
        return "Gümüş"
    if ALTIN.search(ad) or "KIYMETLİ MADEN" in ad:
        return "Altın"
    if "TLREF" in ad:
        return "Para Piyasası (TLREF)"
    if re.search(r"DOLAR|EUROBOND|DÖVİZ|YABANCI|USD|AMERİKA|NASDAQ|S&P", ad):
        return "Döviz / Yabancı"
    if re.search(r"KİRA|BORÇLANMA|DİBS|BONO|TAHVİL|KAMU", ad):
        return "Borçlanma Araçları"
    if re.search(r"BIST|BİST|HİSSE|ENDEKS|TEMETTÜ|BANKA", ad):
        return "Hisse"
    return "Diğer"


# ---------------------------------------------------------------- sayfa verisi
def onceki(sirali, d):
    """sirali listede d'den küçük en büyük değer."""
    lo, hi = 0, len(sirali)
    while lo < hi:
        mid = (lo + hi) // 2
        if sirali[mid] < d:
            lo = mid + 1
        else:
            hi = mid
    return sirali[lo - 1] if lo else None


def sayfa_verisi(depo, kategoriler):
    bulten = sorted(depo["tcmb"])
    tarihler = [d for d in depo["dates"] if d >= BASLANGIC and onceki(bulten, d)]
    konum = [depo["dates"].index(d) for d in tarihler]
    n = len(tarihler)
    usd = [depo["tcmb"][onceki(bulten, d)] for d in tarihler]         # bir önceki iş günü bülteni
    ons_gun = sorted(depo["oz"])

    def hazirla(tip):
        S, bilgi = depo["sets"][tip], depo["info"][tip]
        fonlar = []
        for kod in sorted(S["v"]):
            v = [S["v"][kod][i] for i in konum]
            if not any(v):
                continue
            p = [S["p"][kod][i] for i in konum]
            k = [S["k"][kod][i] for i in konum]
            dolu = [i for i, x in enumerate(v) if x]
            for i in range(dolu[0] + 1, dolu[-1]):                    # aradaki eksik günler önceki değerle
                if not v[i]:
                    v[i] = v[i - 1]
                if not p[i]:
                    p[i] = p[i - 1]
                if not k[i]:
                    k[i] = k[i - 1]
            fonlar.append((kod, S["name"].get(kod, kod), bilgi.get(kod, {}), v, p, k))
        return fonlar

    ham = {t: hazirla(t) for t in TIPLER}

    # altın/gümüş gram fiyatı (TL): önceki günün ons fiyatı × dolar kuru / 31,1035; yoksa altın fonlarından türet
    gram = [[None, None] for _ in range(n)]
    for i, d in enumerate(tarihler):
        og = onceki(ons_gun, d)
        if og and (dt.date.fromisoformat(d) - dt.date.fromisoformat(og)).days <= 6:
            gram[i] = [depo["oz"][og][0] / 31.1035 * usd[i][0], depo["oz"][og][1] / 31.1035 * usd[i][0]]
    for j, desen in ((0, lambda ad: bool(ALTIN.search(ad)) and "GÜMÜŞ" not in ad), (1, lambda ad: "GÜMÜŞ" in ad)):
        ornek = [f[4] for f in ham["YAT"] + ham["BYF"] if desen(f[1]) and "DÖVİZ" not in f[1]]
        for i in range(n):
            if gram[i][j] is None and i and gram[i - 1][j]:
                oran = [p[i] / p[i - 1] for p in ornek if p[i] and p[i - 1]]
                gram[i][j] = gram[i - 1][j] * (statistics.median(oran) if oran else 1)
        for i in range(n - 2, -1, -1):                                # baştaki boşluklar
            if gram[i][j] is None:
                gram[i][j] = gram[i + 1][j]
    fx = [usd[i] + [round(gram[i][0] or 0, 2), round(gram[i][1] or 0, 4)] for i in range(n)]

    setler = {}
    for tip in TIPLER:
        meta, V, P, K = [], [], [], []
        for kod, ad, b, v, p, k in ham[tip]:
            risk = b.get("risk")
            birim, oks = "TL", None
            if tip == "YAT":
                if re.search(r"DÖV[İI]Z", ad):
                    birim = "EUR" if "AVRO" in ad else "GBP" if "POUND" in ad else "USD"
                    s = sorted((oynaklik(p, [x[j] for x in fx]), c) for j, c in enumerate(("USD", "EUR", "GBP")))
                    if all(x[0] for x in s) and s[0][0] < 0.5 * s[1][0]:
                        birim = s[0][1]                               # fiyat hangi kurda düzgünse o
                elif "GÜMÜŞ" in ad:
                    birim = "XAG"
                elif (ALTIN.search(ad) or "KIYMETLİ MADEN" in ad) and "TÜRK ALTIN" not in ad:
                    birim = "XAU"
                kat = kategoriler.get("YAT", {}).get(kod) or yat_kural(ad, b.get("tur"), birim, risk)
                if re.search(r"PARA P[İI]YASASI", ad):
                    kat = "Para Piyasası"
                m = re.match(r"(.*?PORTFÖY)", ad)
                pys = m.group(1) if m else ad.split()[0]
            elif tip == "EMK":
                a = kategoriler.get("EMK", {}).get(kod)
                kat = (a[0] if a and a[0] else None) or emk_kural(ad)
                if "PARA PİYASASI" in ad:
                    kat = "Para Piyasası"
                birim = "XAU" if kat == "Altın" else "XAG" if kat == "Gümüş" else "TL"
                oks = a[1] if a else (1 if "OKS" in ad else 0)
                m = re.match(r"(.*?)\s+(HAYAT VE EMEKLİLİK|EMEKLİLİK VE HAYAT|YAŞAM VE EMEKLİLİK|HAYAT EMEKLİLİK|EMEKLİLİK)", ad)
                pys = (a[2] if a and a[2] else None) or (m.group(1) if m else ad.split()[0])
            else:
                kat = byf_kural(ad)
                birim = "XAU" if kat == "Altın" else "XAG" if kat == "Gümüş" else "TL"
                m = re.match(r"(.*?PORTFÖY)", ad)
                pys = m.group(1) if m else ad.split()[0]
            if kat not in RENK[tip]:
                kat = "Değişken" if tip == "YAT" else "Diğer"
            satir = [kod, ad, kat, birim, pys, 1 if "KATILIM" in ad else 0, 1 if (tip == "YAT" and "ÖZEL" in ad) else 0,
                     1 if b.get("tefas") else 0, risk, b.get("fee")]
            if tip == "EMK":
                satir.append(oks)
            meta.append(satir); V.append(v); P.append(p); K.append(k)
        sira = {m[0]: i for i, m in enumerate(meta)}
        anahtar, kix, pd_gun, pd_veri = [], {}, [], []
        for d in sorted(depo["pd"][tip]):
            if d not in tarihler:
                continue
            dizi = [0] * len(meta)
            for kod, kalem in depo["pd"][tip][d].items():
                if kod not in sira:
                    continue
                a = []
                for kk, deger in kalem.items():
                    if kk not in ETIKET:
                        continue
                    if kk not in kix:
                        kix[kk] = len(anahtar); anahtar.append(ETIKET[kk])
                    a += [kix[kk], deger]
                dizi[sira[kod]] = a
            pd_gun.append(d); pd_veri.append(dizi)
        setler[tip] = {"m": meta, "v": V, "p": P, "k": K, "pd": {"d": pd_gun, "k": anahtar, "s": pd_veri}, "cc": RENK[tip]}
        log(f"{tip}: {len(meta)} fon, son gün toplam {sum(v[-1] for v in V) / 1e9:.2f} Tr TL")
    return {"dates": tarihler, "fx": fx, "sets": setler,
            "updated": dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")}


# ---------------------------------------------------------------- ana akış
def guncelle(depo, bugun: dt.date):
    son = depo["dates"][-1] if depo["dates"] else None
    if son:
        yenile = set(depo["dates"][-3:])                              # geç bildirilen fonlar için son 3 gün yeniden
        ilk = dt.date.fromisoformat(min(yenile))
    else:
        ilk = dt.date.fromisoformat(BASLANGIC)
    gunler = is_gunleri(ilk, bugun)
    log(f"Çekilecek aralık: {gunler[0]} – {gunler[-1]} ({len(gunler)} iş günü)")
    for tip in TIPLER:
        for i in range(0, len(gunler), PARCA[tip]):
            parca = gunler[i:i + PARCA[tip]]
            satirlar = sayfali("fonGnlBlgSiraliGetir", tip, kisa(parca[0]), kisa(parca[-1]), f"{tip} {parca[0]}")
            gunleri_yaz(depo, tip, parca, satirlar)
            log(f"   {tip} {parca[0]} – {parca[-1]}: {len(satirlar)} satır")

    # depoda olup bir fon türü için boş kalan günler (tür sonradan eklendiyse geçmişi): bir kez geriye doğru doldur
    for tip in TIPLER:
        if tip == "YAT":
            continue
        bos = [d for d in depo["dates"] if d >= BASLANGIC and d < gunler[0] and gun_sayisi(depo, "YAT", d) and not gun_sayisi(depo, tip, d)]
        if not bos:
            continue
        log(f"   {tip}: {len(bos)} geçmiş gün boş ({bos[0]} – {bos[-1]}), dolduruluyor")
        for i in range(0, len(bos), PARCA[tip]):
            parca = bos[i:i + PARCA[tip]]
            satirlar = sayfali("fonGnlBlgSiraliGetir", tip, kisa(parca[0]), kisa(parca[-1]), f"{tip} {parca[0]}")
            gunleri_yaz(depo, tip, parca, satirlar)
            log(f"   {tip} {parca[0]} – {parca[-1]}: {len(satirlar)} satır")

    # veri olmayan günleri (tatil) ve henüz tamamlanmamış son günü çıkar
    sayim = {d: gun_sayisi(depo, "YAT", d) for d in depo["dates"]}
    dolu = [c for c in sayim.values() if c]
    orta = statistics.median(dolu) if dolu else 0
    for d in list(depo["dates"]):
        if sayim[d] < 0.5 * orta:
            tarih_sil(depo, d)
    if len(depo["dates"]) >= 2 and depo["dates"][-1] == bugun.isoformat():
        # bugünün verisi gün içinde tamamlanır: dünkü fon değerinin en az %99,7'si bugün de bildirilmiş olmalı
        s, o = depo["dates"][-1], depo["dates"][-2]
        i_s, i_o = depo["dates"].index(s), depo["dates"].index(o)
        V = depo["sets"]["YAT"]["v"].values()
        dun = sum(v[i_o] for v in V)
        gelen = sum(v[i_o] for v in V if v[i_s])
        if not dun or gelen < 0.997 * dun:
            log(f"{s} verisi henüz tamamlanmamış (fon değerinin %{100 * gelen / max(dun, 1):.1f}'i geldi); sonraki çalışmada eklenecek")
            tarih_sil(depo, s)
    if not depo["dates"]:
        raise RuntimeError("TEFAS'tan hiç veri gelmedi")
    log(f"Depoda {len(depo['dates'])} gün var; son veri tarihi {depo['dates'][-1]}")

    # fon bilgileri: tür, risk, yönetim ücreti
    donem = {"basTarih": None, "bitTarih": None, "calismaTipi": 2, "getiriOrani": "1", "donemGetiri1a": "1",
             "donemGetiri3a": "1", "donemGetiri6a": "1", "donemGetiriyb": "1", "donemGetiri1y": "1",
             "donemGetiri3y": "1", "donemGetiri5y": "1"}
    for tip in TIPLER:
        bilgi = depo["info"][tip]
        for x in tefas("fonGetiriBazliBilgiGetir", {**govde_temel(tip), **donem}, f"{tip} getiri")["resultList"]:
            r = str(x.get("riskDegeri") or "")
            b = bilgi.setdefault(x["fonKodu"], {})
            b.update({"tur": x.get("fonTurAciklama"), "tefas": bool(x.get("tefasDurum")),
                      "risk": int(r) if r.isdigit() and r != "0" else None})
        for x in tefas("fonYonetimBazliBilgiGetir", govde_temel(tip), f"{tip} ücret")["resultList"]:
            bilgi.setdefault(x["fonKodu"], {})["fee"] = ucret(x.get("uygulananYu1Y"), x.get("fonIcTuzukYu1G"))

    # portföy dağılımı: her ayın son günü ve en güncel gün
    ay_sonu = {}
    for d in depo["dates"]:
        if d >= "2025-12-31":
            ay_sonu[d[:7]] = d
    gerekli = set(ay_sonu.values()) | {depo["dates"][-1]}
    for tip in TIPLER:
        pd = depo["pd"][tip]
        for d in [x for x in pd if x not in gerekli]:
            del pd[d]
        for d in sorted(gerekli - set(pd)):
            satirlar = tefas("dagilimSiraliGetirT", govde_liste(tip, kisa(d), kisa(d), 1, 6000), f"{tip} dağılım {d}")["resultList"]
            pd[d] = {x["fonKodu"]: {k: v for k, v in x.items() if k not in PD_ATLA and v} for x in satirlar}
            log(f"   {tip} portföy dağılımı {d}: {len(satirlar)} fon")
        if not pd.get(depo["dates"][-1]):                             # son gün henüz yayımlanmadıysa bir sonraki çalışmada
            pd.pop(depo["dates"][-1], None)


def main():
    sifre = os.environ.get("SITE_PASSWORD", "")
    if len(sifre) < 6:
        log("HATA: SITE_PASSWORD tanımlı değil ya da 6 karakterden kısa. Depo ayarlarından ekleyin.")
        return 2
    os.makedirs(SITE, exist_ok=True)
    yol = os.path.join(SITE, "store.enc")
    if os.path.exists(yol):
        try:
            depo = coz(open(yol, "rb").read(), sifre)
            log(f"Önceki veri yüklendi: {len(depo['dates'])} gün, son {depo['dates'][-1]}")
        except Exception as e:
            log(f"Önceki veri açılamadı ({type(e).__name__}); şifre değişmiş olabilir. Sıfırdan çekiliyor.")
            depo = bos_depo()
    else:
        log("Önceki veri yok; ilk kurulum, tüm dönem çekilecek (10-20 dakika sürebilir).")
        depo = bos_depo()

    bugun = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)).date()     # Türkiye saati
    guncelle(depo, bugun)
    tcmb_cek(depo, bugun)
    if not depo["tcmb"]:
        raise RuntimeError("TCMB kurları alınamadı")
    metal_cek(depo)

    kategoriler = json.load(open("kategoriler.json", encoding="utf-8")) if os.path.exists("kategoriler.json") else {}
    veri = sayfa_verisi(depo, kategoriler)
    if not veri["dates"]:
        raise RuntimeError("Sayfa verisi boş")
    open(yol, "wb").write(sifrele(depo, sifre))
    # sayfa verisi şifresiz yayımlanır (site herkese açık); store.enc yalnızca iş akışının iç deposu
    json.dump(veri, open(os.path.join(SITE, "data.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    if os.path.exists(os.path.join(SITE, "data.enc")):
        os.remove(os.path.join(SITE, "data.enc"))
    open(os.path.join(SITE, "tefas.html"), "w", encoding="utf-8").write(open("sayfa.html", encoding="utf-8").read())
    open(os.path.join(SITE, ".nojekyll"), "w").write("")
    try:                                                             # üst başlıktaki "güncel" göstergesi
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ortak"))
        from durum import yaz
        yaz(SITE, "tefas", veri["dates"][-1])
    except Exception as e:
        log(f"durum.json yazılamadı: {e}")
    log(f"TAMAM — son veri tarihi {veri['dates'][-1]}, güncelleme {veri['updated']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
