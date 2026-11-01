"""ALCO – Bankacılık Verileri: BDDK haftalık / aylık bülten ve TCMB EVDS verisini günceller.

Her çalıştığında:
  1) site/bankacilik/data/*.enc.json varsa şifresini çözer (önceki çalışmaların verisi),
     yoksa bankacilik/baslangic.json.gz'den başlar
  2) --cek verilmişse eksik haftaları, ayları ve EVDS serilerini çeker
     (her kaynak ayrı denenir; biri başarısız olursa diğerleri ve önceki veri korunur)
  3) Veriyi şifreler, sayfayı menüyle birlikte site/bankacilik/ altına yazar

Şifre SITE_PASSWORD, EVDS anahtarı EVDS_API_KEY ortam değişkeninden okunur.
"""
import argparse
import base64
import datetime as dt
import gzip
import json
import os
import re
import sys
import tempfile
import time
from html.parser import HTMLParser

import certifi
import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

KOK = os.path.dirname(os.path.abspath(__file__))
DOSYALAR = ("bddk_haftalik", "bddk_aylik", "evds", "politika")
ITER = 250_000
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BDDK_H = "https://www.bddk.org.tr/BultenHaftalik"
BDDK_A = "https://www.bddk.org.tr/BultenAylik/tr/Home/BasitRaporGetir"
EVDS = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
AYLAR = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6, "Temmuz": 7,
         "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}


def log(*a):
    print(*a, flush=True)


def simdi():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ---------------------------------------------------------------- şifreleme (sayfanın beklediği biçim)
def _anahtar(sifre, tuz, it=ITER):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=tuz, iterations=it).derive(sifre.encode("utf-8"))


def sifrele(nesne, sifre):
    ham = gzip.compress(json.dumps(nesne, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    tuz, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_anahtar(sifre, tuz)).encrypt(iv, ham, None)
    b = lambda x: base64.b64encode(x).decode("ascii")
    return {"v": 1, "iter": ITER, "salt": b(tuz), "iv": b(iv), "ct": b(ct)}


def coz(env, sifre):
    d = lambda x: base64.b64decode(x)
    ham = AESGCM(_anahtar(sifre, d(env["salt"]), env.get("iter", ITER))).decrypt(d(env["iv"]), d(env["ct"]), None)
    return json.loads(gzip.decompress(ham))


# ---------------------------------------------------------------- BDDK oturumu
def bddk_oturum():
    """BDDK ara sertifikayı göndermiyor; certifi + o ara sertifika ile doğrulanır (doğrulama kapatılmaz)."""
    paket = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
    paket.write(open(certifi.where()).read() + "\n" + open(os.path.join(KOK, "bddk_ara_sertifika.pem")).read())
    paket.close()
    s = requests.Session()
    s.verify = paket.name
    s.headers.update({"User-Agent": UA})
    return s


def sayi(t):
    t = (t or "").strip().replace("\xa0", "")
    if t in ("", "-"):
        return None
    try:
        return float(t.replace(".", "").replace(",", "."))
    except ValueError:
        return None


class Sayfa(HTMLParser):
    """Haftalık bülten sayfasından form jetonlarını, dönem listesini ve #TabloExcel tablosunu okur."""

    def __init__(self):
        super().__init__()
        self.form = None
        self.jeton = {}
        self.donem = []          # [(id, yil, metin)]
        self._opt = None
        self.tablo = []          # [[hücre metinleri]]
        self._t = 0
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "form":
            self.form = a.get("action")
        elif tag == "input" and a.get("name") == "__RequestVerificationToken" and self.form:
            self.jeton[self.form] = a.get("value")
        elif tag == "option" and "YilDonem" in (a.get("class") or ""):
            yil = re.search(r"Yil-(\d{4})", a.get("class") or "")
            self._opt = [a.get("value"), yil.group(1) if yil else None, ""]
        elif tag == "table":
            if a.get("id") == "TabloExcel":
                self._t = 1
            elif self._t:
                self._t += 1
        elif self._t == 1 and tag == "tr":
            self._row = []
        elif self._t == 1 and tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "form":
            self.form = None
        elif tag == "option" and self._opt:
            self._opt[2] = self._opt[2].strip()
            self.donem.append(tuple(self._opt))
            self._opt = None
        elif self._t and tag == "table":
            self._t -= 1
        elif self._t == 1 and tag in ("td", "th") and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif self._t == 1 and tag == "tr" and self._row is not None:
            self.tablo.append(self._row)
            self._row = None

    def handle_data(self, d):
        if self._opt is not None:
            self._opt[2] += d
        if self._cell is not None:
            self._cell.append(d)


def bddk_haftalik(D):
    s = bddk_oturum()
    r = s.get(BDDK_H + "/", timeout=60)
    r.raise_for_status()
    p = Sayfa()
    p.feed(r.text)
    jeton = dict(p.jeton)
    if not p.donem:
        raise RuntimeError("haftalık bülten dönem listesi okunamadı")
    son = max(int(i) for i in D["weeks"])
    yeni = sorted(((int(i), y) for i, y, _ in p.donem if i and int(i) > son), key=lambda x: x[0])
    yeni = [(son, D["weeks"][str(son)][:4])] + yeni          # son haftayı da tazele (düzeltme olabilir)
    log(f"BDDK haftalık: kayıtlı son hafta {son}, çekilecek {[i for i, _ in yeni]}")

    def gonder(yol, alanlar):
        tok = jeton.get(yol)
        if not tok:
            raise RuntimeError(f"form jetonu yok: {yol}")
        rr = s.post("https://www.bddk.org.tr" + yol, data={"__RequestVerificationToken": tok, **alanlar}, timeout=60)
        rr.raise_for_status()
        pp = Sayfa()
        pp.feed(rr.text)
        jeton.update(pp.jeton)
        time.sleep(0.4)
        return pp

    for wid, yil in yeni:
        gonder("/BultenHaftalik/tr/Home/DonemDegistir", {"yil": yil, "donemId": str(wid), "para": "TL"})
        hafta = {}
        tarih = None
        for g in D["groups"]:
            gonder("/BultenHaftalik/tr/Home/TarafSec", {"tarafKodu": g["code"]})
            hafta[g["key"]] = {}
            for t in D["tables"]:
                pp = gonder("/BultenHaftalik/", {"tabloId": str(t["id"])})
                if not pp.tablo:
                    raise RuntimeError(f"tablo boş: hafta {wid} {g['key']} {t['key']}")
                baslik = pp.tablo[0][1] if len(pp.tablo[0]) > 1 else ""
                m = re.search(r"(\d{1,2}) (\w+) (\d{4})", baslik)
                if m and m.group(2) in AYLAR:
                    tarih = f"{m.group(3)}-{AYLAR[m.group(2)]:02d}-{int(m.group(1)):02d}"
                if "Milyon TL" not in baslik:
                    raise RuntimeError(f"para birimi TL değil: {baslik}")
                satir = {}
                for row in pp.tablo[1:]:
                    if len(row) < 3 or not row[0].strip().isdigit():
                        continue
                    satir[row[0].strip()] = [sayi(x) for x in row[2:]]
                hafta[g["key"]][t["key"]] = satir
        if not tarih:
            raise RuntimeError(f"hafta {wid} tarihi okunamadı")
        D["weeks"][str(wid)] = tarih
        D["values"][str(wid)] = hafta
        log(f"   hafta {wid} ({tarih}) tamam")
    D["updated"] = simdi()


def bddk_aylik(D):
    s = bddk_oturum()
    son = max(D["values"])
    y, m = map(int, son.split("-"))
    aylar = [(y, m)]                                          # son ayı da tazele
    for _ in range(3):
        m += 1
        if m > 12:
            y, m = y + 1, 1
        aylar.append((y, m))
    for (y, m) in aylar:
        anahtar = f"{y}-{m:02d}"
        ay = {}
        for g in D["groups"]:
            ay[g["key"]] = {}
            for t in D["tables"]:
                r = s.post(BDDK_A, data={"tabloNo": str(t["no"]), "yil": str(y), "ay": str(m), "paraBirimi": "TL", "taraf": g["code"]}, timeout=60)
                r.raise_for_status()
                j = r.json()
                time.sleep(0.3)
                if not j.get("success"):
                    hata = str(j.get("error") or "")
                    if "en son" in hata or "başlamaktadır" in hata:
                        log(f"BDDK aylık: {anahtar} henüz yayımlanmamış")
                        D["updated"] = simdi()
                        return
                    raise RuntimeError(f"aylık tablo {t['no']} {anahtar}: {hata}")
                satir = {}
                for row in j["Json"]["data"]["rows"]:
                    c = row["cell"]
                    satir[str(c[1])] = [None if v in (None, "") else float(v) for v in c[4:]]
                ay[g["key"]][str(t["no"])] = satir
        D["values"][anahtar] = ay
        log(f"BDDK aylık: {anahtar} tamam")
    D["updated"] = simdi()


# Başlangıç verisinde olmayan, sonradan eklenen EVDS grupları: ilk çalışmada geçmişiyle birlikte çekilir.
# (bölüm adı, listede hangi grubun ardına ekleneceği, grup tanımı)
EK_GRUPLAR = [
    ("Para ve Banka İstatistikleri (Haftalık)", "bie_hpbitablo4", {
        "code": "bie_hpbitablo5", "name": "Yabancı Para Mevduatta Haftalık Değişim ve Parite Etkisi (Yurt İçi Şubeler)",
        "freq": "HAFTALIK(CUMA)", "unit": "milyon ABD doları", "akim": True, "series": [
            {"code": "TP.HPBITABLO5.1", "name": "1.Parite Etkisinden Arındırılmış Değişim (Yurt İçi Yerleşikler)"},
            {"code": "TP.HPBITABLO5.2", "name": "1.1.Gerçek Kişiler"},
            {"code": "TP.HPBITABLO5.3", "name": "1.1.1.ABD Doları Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.4", "name": "1.1.2.Euro Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.5", "name": "1.1.3.Diğer Para Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.6", "name": "1.1.4.Kıymetli Maden Depo Hesapları"},
            {"code": "TP.HPBITABLO5.7", "name": "1.2.Tüzel Kişiler"},
            {"code": "TP.HPBITABLO5.8", "name": "1.2.1.ABD Doları Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.9", "name": "1.2.2.Euro Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.10", "name": "1.2.3.Diğer Para Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.11", "name": "1.2.4.Kıymetli Maden Depo Hesapları"},
            {"code": "TP.HPBITABLO5.12", "name": "2.Parite Etkisi (Yurt İçi Yerleşikler)"},
            {"code": "TP.HPBITABLO5.13", "name": "2.1.Gerçek Kişiler"},
            {"code": "TP.HPBITABLO5.14", "name": "2.1.1.ABD Doları Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.15", "name": "2.1.2.Euro Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.16", "name": "2.1.3.Diğer Para Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.17", "name": "2.1.4.Kıymetli Maden Depo Hesapları"},
            {"code": "TP.HPBITABLO5.18", "name": "2.2.Tüzel Kişiler"},
            {"code": "TP.HPBITABLO5.19", "name": "2.2.1.ABD Doları Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.20", "name": "2.2.2.Euro Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.21", "name": "2.2.3.Diğer Para Cinsi Mevduat"},
            {"code": "TP.HPBITABLO5.22", "name": "2.2.4.Kıymetli Maden Depo Hesapları"}]}),
]


def evds(D, anahtar):
    s = requests.Session()
    s.headers.update({"key": anahtar, "User-Agent": UA})
    bugun = dt.date.today()
    hatali = []
    for bolum, sonra, tanim in EK_GRUPLAR:
        if tanim["code"] in D["groups"]:
            continue
        D["groups"][tanim["code"]] = {**tanim, "updated": "", "dates": [], "vals": {}}
        for b in D.get("tree", []):
            if b.get("section") == bolum and tanim["code"] not in b["groups"]:
                i = b["groups"].index(sonra) + 1 if sonra in b["groups"] else len(b["groups"])
                b["groups"].insert(i, tanim["code"])
        log(f"   EVDS {tanim['code']}: yeni grup eklendi, geçmişiyle çekilecek")
    for kod, g in D["groups"].items():
        aylik = g["freq"].upper().startswith("AYLIK")
        bas = bugun - dt.timedelta(days=400 if aylik else 180)
        if not g["dates"]:                                             # yeni grup: aynı sıklıktaki grupların başlangıcından
            ilk = [x["dates"][0] for x in D["groups"].values() if x["dates"] and x["freq"] == g["freq"]]
            bas = dt.date(2022, 12, 1) if not ilk else (dt.date(int(min(ilk)[:4]), int(min(ilk)[5:7]), 1))
        seriler = [x["code"] for x in g["series"]]
        try:
            yeni = {}
            for i in range(0, len(seriler), 40):                       # uzun URL'yi parçala
                parca = seriler[i:i + 40]
                url = (EVDS + f"series={'-'.join(parca)}&startDate={bas:%d-%m-%Y}&endDate={bugun:%d-%m-%Y}&type=json")
                r = s.get(url, timeout=90, allow_redirects=False)
                if r.status_code == 403:
                    raise RuntimeError("EVDS anahtarı reddedildi (EVDS_API_KEY)")
                r.raise_for_status()
                for it in r.json().get("items", []):
                    t = it.get("Tarih", "")
                    if aylik:
                        mm = re.match(r"^(\d{4})-(\d{1,2})$", t)
                        if not mm:
                            continue
                        tarih = f"{mm.group(1)}-{int(mm.group(2)):02d}"
                    else:
                        mm = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", t)
                        if not mm:
                            continue
                        tarih = f"{mm.group(3)}-{mm.group(2)}-{mm.group(1)}"
                    for c in parca:
                        v = it.get(c.replace(".", "_"))
                        if v not in (None, "", "ND"):
                            try:
                                yeni.setdefault(tarih, {})[c] = float(v)
                            except (TypeError, ValueError):
                                pass
                time.sleep(0.3)
            if not yeni:
                log(f"   EVDS {kod}: yeni veri yok")
                continue
            tarihler = sorted(set(g["dates"]) | set(yeni))
            eski = {c: dict(zip(g["dates"], g["vals"].get(c, []))) for c in seriler}
            for t, vs in yeni.items():
                for c, v in vs.items():
                    eski[c][t] = v
            g["dates"] = tarihler
            g["vals"] = {c: [eski[c].get(t) for t in tarihler] for c in seriler}
            log(f"   EVDS {kod}: son tarih {tarihler[-1]}")
        except Exception as e:
            log(f"   EVDS {kod}: HATA {type(e).__name__}: {e}")
            hatali.append(kod)
    D["failed"] = hatali
    D["updated"] = simdi()
    if len(hatali) == len(D["groups"]):
        raise RuntimeError("EVDS: hiçbir grup çekilemedi")


# ---------------------------------------------------------------- para politikası
TCMB = "https://www.tcmb.gov.tr"
PP_GUNLUK = {           # anahtar: EVDS serisi (iş günü)
    "fon_top": "TP.APIFON1.TOP", "fon_iha": "TP.APIFON1.IHA", "fon_kot": "TP.APIFON1.KOT.T",
    "fon_bist": "TP.APIFON1.KOT.A", "fon_tldepo": "TP.APIFON1.KOT.B", "fon_glp": "TP.APIFON1.KOT.C",
    "st_top": "TP.APIFON2.TOP", "st_iha": "TP.APIFON2.IHA", "st_kot": "TP.APIFON2.KOT", "st_lik": "TP.APIFON2.LIK",
    "net": "TP.APIFON3", "aof": "TP.APIFON4",
    "usdtry": "TP.DK.USD.A.YTL",
    # TCMB taraflı swap stokları (milyon USD)
    "sw_usd_piy": "TP.SWAPTEKTAR.SWAPKSTOKUSDTUTAR", "sw_usd_bist": "TP.SWAPTEKTAR.BISWAPSTOKUSDTUTAR",
    "sw_usd_al": "TP.SWAPTEKTAR.SWAPPALIMSTOKUSDTUTAR", "sw_usd_sat": "TP.SWAPTEKTAR.SWAPPSATIMSTOKUSDTUTAR",
    "sw_usd_mik": "TP.SWAPTEKTAR.SWAPMSTOKUSDTUTAR",
    "sw_xau_piy": "TP.SWAPTEKTAR.SWAPASTOKUSDTUTAR", "sw_xau_al": "TP.SWAPTEKTAR.SWAPXALIMSTOKUSDTUTAR",
    "sw_xau_sat": "TP.SWAPTEKTAR.SWAPXSATIMSTOKUSDTUTAR",
    "sw_top_al": "TP.SWAPTEKTAR.TOTALSTOKALIMYONLU", "sw_top_sat": "TP.SWAPTEKTAR.TOTALSTOKSATIMYONLU",
}
PP_BASLANGIC = dt.date(2022, 12, 1)
AYLAR_TR = {k.lower(): v for k, v in AYLAR.items()}


def evds_cek(s, kodlar, bas, bit, aylik=False):
    """{tarih: {kod: değer}}; EVDS 1000 satır sınırı için 1 yıllık pencerelerle."""
    out = {}
    while bas <= bit:
        son = min(bit, bas + dt.timedelta(days=364))
        for i in range(0, len(kodlar), 20):
            parca = kodlar[i:i + 20]
            url = EVDS + f"series={'-'.join(parca)}&startDate={bas:%d-%m-%Y}&endDate={son:%d-%m-%Y}&type=json"
            r = s.get(url, timeout=120, allow_redirects=False)
            if r.status_code == 403:
                raise RuntimeError("EVDS anahtarı reddedildi (EVDS_API_KEY)")
            r.raise_for_status()
            for it in r.json().get("items", []):
                t = it.get("Tarih", "")
                if aylik:
                    mm = re.match(r"^(\d{4})-(\d{1,2})$", t)
                    tarih = f"{mm.group(1)}-{int(mm.group(2)):02d}" if mm else None
                else:
                    mm = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", t)
                    tarih = f"{mm.group(3)}-{mm.group(2)}-{mm.group(1)}" if mm else None
                if not tarih:
                    continue
                for c in parca:
                    v = it.get(c.replace(".", "_"))
                    if v not in (None, "", "ND"):
                        try:
                            out.setdefault(tarih, {})[c] = float(v)
                        except (TypeError, ValueError):
                            pass
            time.sleep(0.3)
        bas = son + dt.timedelta(days=1)
    return out


def tcmb_get(s, yol):
    r = s.get(TCMB + yol, timeout=60)
    r.raise_for_status()
    return r.text


def hucreler(html):
    """Basit tablo okuyucu: [[(metin, href), ...], ...]"""
    satirlar = []
    for tr in re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", html, re.I):
        hs = []
        for td in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", tr, re.I):
            href = re.search(r'href="([^"]+)"', td)
            metin = re.sub(r"<[^>]+>", " ", td)
            metin = re.sub(r"\s+", " ", metin.replace("&nbsp;", " ")).strip()
            hs.append((metin, href.group(1) if href else None))
        if hs:
            satirlar.append(hs)
    return satirlar


def tr_tarih(metin):
    m = re.search(r"(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{4})", metin)
    if not m or m.group(2).lower() not in AYLAR_TR:
        return None
    return f"{m.group(3)}-{AYLAR_TR[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"


def politika(P, anahtar):
    s = requests.Session()
    s.headers.update({"key": anahtar, "User-Agent": UA})
    bugun = dt.date.today()
    # 1) günlük EVDS serileri: ilk çalışmada 2022 sonundan, sonra son 90 gün
    g = P.setdefault("daily", {"dates": [], "series": {}})
    bas = PP_BASLANGIC if not g["dates"] else dt.date.fromisoformat(g["dates"][-1]) - dt.timedelta(days=90)
    yeni = evds_cek(s, list(PP_GUNLUK.values()), bas, bugun)
    if not yeni and not g["dates"]:
        raise RuntimeError("para politikası serileri boş geldi")
    eski = {k: dict(zip(g["dates"], g["series"].get(k, []))) for k in PP_GUNLUK}
    for t, vs in yeni.items():
        for k, kod in PP_GUNLUK.items():
            if kod in vs:
                eski[k][t] = vs[kod]
    tarihler = sorted(set(g["dates"]) | {t for t, vs in yeni.items() if PP_GUNLUK["fon_top"] in vs or PP_GUNLUK["st_top"] in vs})
    g["dates"] = tarihler
    g["series"] = {k: [eski[k].get(t) for t in tarihler] for k in PP_GUNLUK}
    log(f"   para politikası: {len(tarihler)} gün, son {tarihler[-1] if tarihler else '-'}")
    # 2) TÜFE endeksi (aylık, yıllık değişim için)
    tf = evds_cek(s, ["TP.FG.J0"], dt.date(2021, 1, 1), bugun, aylik=True)
    if tf:
        P["tufe"] = {t: v["TP.FG.J0"] for t, v in sorted(tf.items()) if "TP.FG.J0" in v}
    # 3) politika faizi (1 hafta repo) ve PPK takvimi: TCMB sitesi
    w = requests.Session()
    w.headers.update({"User-Agent": UA})
    try:
        h = tcmb_get(w, "/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Temel+Faaliyetler/Para+Politikasi/Merkez+Bankasi+Faiz+Oranlari/1+Hafta+Repo")
        faiz = []
        for row in hucreler(h):
            m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", row[0][0]) if row else None
            if m and len(row) >= 3:
                try:
                    faiz.append({"tarih": f"{m.group(3)}-{m.group(2)}-{m.group(1)}", "oran": float(row[2][0].replace(",", "."))})
                except ValueError:
                    pass
        if len(faiz) > 10:
            P["faiz"] = faiz
            log(f"   politika faizi: {len(faiz)} değişiklik, son {faiz[-1]}")
    except Exception as e:
        log(f"   politika faizi okunamadı: {type(e).__name__}: {e}")
    ppk = P.setdefault("ppk", {})
    for yil in range(2023, bugun.year + 2):
        try:
            h = tcmb_get(w, f"/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Temel+Faaliyetler/Para+Politikasi/PPK/{yil}")
        except Exception as e:
            log(f"   PPK {yil}: {type(e).__name__}")
            continue
        top = []
        for row in hucreler(h):
            t = tr_tarih(row[0][0]) if row else None
            if not t or not t.startswith(str(yil)):
                continue
            top.append({"tarih": t, "ara": "*" in row[0][0], "url": (TCMB + row[0][1]) if row[0][1] and row[0][1].startswith("/") else row[0][1],
                        "ozet": tr_tarih(row[1][0]) if len(row) > 1 else None})
        if top:
            ppk[str(yil)] = top
    log(f"   PPK takvimi: {', '.join(f'{y}:{len(v)}' for y, v in sorted(ppk.items()))}")
    P["updated"] = simdi()


# ---------------------------------------------------------------- sayfa
MENU = '<div id="alcoTop"></div><script src="../ortak/ust.js" data-page="banka" data-root="../"></script>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cek", action="store_true", help="BDDK ve EVDS'den yeni veriyi çek")
    ap.add_argument("--site", default="site")
    a = ap.parse_args()
    sifre = os.environ.get("SITE_PASSWORD", "")      # yalnızca eski şifreli dosyaları bir kez açmak için
    cikti = os.path.join(a.site, "bankacilik")
    veri_dizin = os.path.join(cikti, "data")
    os.makedirs(veri_dizin, exist_ok=True)

    tohum = None
    D = {}
    for f in DOSYALAR:
        yol = os.path.join(veri_dizin, f + ".enc.json")
        duz = os.path.join(veri_dizin, f + ".json")
        try:
            D[f] = json.load(open(duz, encoding="utf-8")) if os.path.exists(duz) else coz(json.load(open(yol)), sifre)
            log(f"Önceki veri: {f}")
        except Exception as e:
            if os.path.exists(yol):
                log(f"Önceki {f} açılamadı ({type(e).__name__}); başlangıç verisi kullanılıyor.")
            if tohum is None:
                tohum = json.loads(gzip.decompress(open(os.path.join(KOK, "baslangic.json.gz"), "rb").read()))
            D[f] = tohum.get(f, {})

    sorun = []
    if a.cek:
        for ad, fn in (("bddk_haftalik", lambda: bddk_haftalik(D["bddk_haftalik"])),
                       ("bddk_aylik", lambda: bddk_aylik(D["bddk_aylik"])),
                       ("evds", lambda: evds(D["evds"], os.environ.get("EVDS_API_KEY", ""))),
                       ("politika", lambda: politika(D["politika"], os.environ.get("EVDS_API_KEY", "")))):
            if ad in ("evds", "politika") and not os.environ.get("EVDS_API_KEY"):
                log("EVDS: EVDS_API_KEY tanımlı değil, atlandı.")
                sorun.append(ad)
                continue
            try:
                log(f"== {ad}")
                fn()
            except Exception as e:
                log(f"HATA {ad}: {type(e).__name__}: {e} — önceki veri korunuyor")
                sorun.append(ad)

    for f in DOSYALAR:
        json.dump(D[f], open(os.path.join(veri_dizin, f + ".json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        if os.path.exists(os.path.join(veri_dizin, f + ".enc.json")):
            os.remove(os.path.join(veri_dizin, f + ".enc.json"))
    try:                                                             # Yatırım Vekaleti piyasa verisi (elle yüklenen Excel)
        sys.path.insert(0, KOK)
        import yv
        g = yv.derle(os.path.join(KOK, "yv"))
        yol = os.path.join(veri_dizin, "yv.json")
        if g:
            json.dump({"groups": {g["code"]: g}}, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            log(f"Yatırım vekaleti: {len(g['series'])} seri, son {g['dates'][-1]}")
        elif os.path.exists(yol):
            os.remove(yol)
    except Exception as e:
        log(f"Yatırım vekaleti verisi derlenemedi: {type(e).__name__}: {e}")
    html = open(os.path.join(KOK, "sayfa.html"), encoding="utf-8").read()
    html = html.replace("/*PARA_POLITIKASI*/", open(os.path.join(KOK, "para_politikasi.js"), encoding="utf-8").read(), 1)
    html = html.replace("<body>", "<body>" + MENU, 1) if "<body>" in html else MENU + html
    open(os.path.join(cikti, "index.html"), "w", encoding="utf-8").write(html)
    try:                                                             # üst başlıktaki "güncel" göstergesi
        sys.path.insert(0, os.path.join(os.path.dirname(KOK), "ortak"))
        from durum import yaz
        h_ = D["bddk_haftalik"]
        if h_.get("weeks"):
            yaz(a.site, "bddk_haftalik", max(h_["weeks"].values()))
        if D["bddk_aylik"].get("values"):
            yaz(a.site, "bddk_aylik", max(D["bddk_aylik"]["values"]))
        ed = [g["dates"][-1] for g in (D["evds"].get("groups") or {}).values() if g.get("dates") and len(g["dates"][-1]) == 10]
        if ed:
            yaz(a.site, "evds", max(ed))
        P = D.get("politika") or {}
        if P.get("daily", {}).get("dates"):
            yaz(a.site, "politika", P["daily"]["dates"][-1])
        bugun = dt.date.today().isoformat()
        sonraki = sorted(x["tarih"] for v in (P.get("ppk") or {}).values() for x in v if x["tarih"] >= bugun)
        yaz(a.site, "", None, ppk_sonraki=sonraki[0] if sonraki else None)
    except Exception as e:
        log(f"durum.json yazılamadı: {e}")
    h = D["bddk_haftalik"]
    log(f"TAMAM — haftalık son {max(h['weeks'].values())}, aylık son {max(D['bddk_aylik']['values'])}"
        + (f"; sorunlu: {', '.join(sorun)}" if sorun else ""))
    return 1 if a.cek and len(sorun) == len(DOSYALAR) else 0


if __name__ == "__main__":
    sys.exit(main())
