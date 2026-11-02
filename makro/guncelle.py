"""Makro ve Piyasa Verileri: veri çekici.

Kaynaklar
  - TÜİK Veri Portalı haber bültenleri (TÜFE, Yİ-ÜFE): manşet oranlar ve TÜFE ana harcama grubu kırılımı
  - TCMB EVDS: Piyasa Katılımcıları Anketi (cari yıl sonu / 12 ay sonrası TÜFE beklentisi),
    sektörel enflasyon beklentileri (piyasa, reel sektör, hanehalkı 12 ay sonrası)
  - TCMB: enflasyon hedefleri tablosu ve en güncel Enflasyon Raporu'ndaki yıl sonu tahminleri / ara hedefler
  - Borsa İstanbul: TLREF ve TLREFK
  - Borsa İstanbul Repo Pazarı O/N (EVDS): ağırlıklı ortalama oran ve hacim

Kullanım: python makro/guncelle.py --site site   (EVDS anahtarı EVDS_API_KEY ortam değişkeninden)
Önceki çıktı (site/makro/data/makro.json) varsa üzerine eklenir; bir kaynak çekilemezse eski verisi korunur.
"""
import argparse
import datetime as dt
import html as htmlmod
import io
import json
import os
import re
import sys
import time

import requests

KOK = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
EVDS = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
TUIK = "https://veriportali.tuik.gov.tr"
TCMB = "https://www.tcmb.gov.tr"
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def log(*a):
    print(*a, flush=True)


def simdi():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def oturum():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"})
    return s


def sayi(t):
    t = str(t).strip().replace("\xa0", "")
    if t in ("", "-", "–"):
        return None
    t = t.replace(".", "").replace(",", ".") if "," in t else t
    try:
        return float(t)
    except ValueError:
        return None


def ay_kodu(donem):
    """'Eylül 2026' -> '2026-09'"""
    m = re.match(r"\s*(\S+)\s+(\d{4})", donem or "")
    if not m or m.group(1) not in AYLAR:
        return None
    return f"{m.group(2)}-{AYLAR.index(m.group(1)) + 1:02d}"


def ay_kaydir(ay, n):
    y, m = int(ay[:4]), int(ay[5:7]) + n
    while m < 1:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return f"{y}-{m:02d}"


# ------------------------------------------------------------------ TÜİK
def tuik_bulten(s, pid):
    r = s.get(f"{TUIK}/api/tr/press/{pid}", headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    j = r.json()
    if j.get("isError") or not j.get("data"):
        raise RuntimeError(f"TÜİK bülten {pid}: {j.get('message')}")
    return j["data"]


def tuik_grafikler(icerik):
    out = []
    for m in re.finditer(r'data-options="([^"]*)"', icerik):
        try:
            out.append(json.loads(htmlmod.unescape(m.group(1)).replace("'", '"')))
        except Exception:
            pass
    return out


def tuik_ilk_tablo(icerik):
    """Bültenin ilk tablosu: başlıkta 3 dönem (bu ay, geçen yıl aynı ay, iki yıl önce), satırlarda aylık / aralık / yıllık / 12 ay ort."""
    m = re.search(r"<table[\s\S]*?</table>", icerik)
    if not m:
        return {}
    satirlar = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", m.group(0)):
        hucre = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<t[hd][^>]*>([\s\S]*?)</t[hd]>", tr)]
        satirlar.append(hucre)
    if not satirlar:
        return {}
    donemler = [ay_kodu(h) for h in satirlar[0][1:]]
    anahtar = (("aya göre", "mom"), ("Aralık", "ytd"), ("aynı ayına", "yoy"), ("ortalama", "avg12"))
    out = {}
    for h in satirlar[1:]:
        k = next((v for a, v in anahtar if a in (h[0] if h else "")), None)
        if not k:
            continue
        for d, v in zip(donemler, h[1:]):
            if d:
                out.setdefault(d, {})[k] = sayi(v)
    return out


def tuik_seri(s, baslik, onceki, ay_sayisi=40, kirilim=False):
    """baslik: TÜİK bülten adı. onceki: önceki çıktı {months:..., ...}. Yeni bültenleri geriye doğru gezerek ekler."""
    r = s.get(f"{TUIK}/api/tr/press", headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    son = next((x for x in r.json().get("data", []) if x.get("title") == baslik), None)
    if not son:
        raise RuntimeError(f"TÜİK: '{baslik}' bülteni listede yok")
    veri = {}                                            # ay -> {mom, ytd, yoy, avg12}
    for i, ay in enumerate(onceki.get("months", [])):
        veri[ay] = {k: onceki.get(k, [None] * 999)[i] for k in ("mom", "ytd", "yoy", "avg12")}
    bultenler = dict(onceki.get("press", {}))           # ay -> bülten no
    gruplar = dict(onceki.get("groups", {})) if kirilim else {}
    kuyruk, gorulen, sinir = [str(son["id"])], set(), None
    while kuyruk:
        pid = kuyruk.pop(0)
        if pid in gorulen:
            continue
        gorulen.add(pid)
        d = tuik_bulten(s, pid)
        ay = ay_kodu(d.get("period"))
        if not ay:
            continue
        sinir = sinir or ay_kaydir(ay, -ay_sayisi)
        tablo = tuik_ilk_tablo(d.get("content", ""))
        for a, v in tablo.items():
            if a == ay or a not in veri or any(veri[a].get(k) is None for k in v):
                veri.setdefault(a, {}).update({k: x for k, x in v.items() if x is not None})
        bultenler[ay] = int(d.get("number") or pid)
        if kirilim:
            g = {}
            for o in tuik_grafikler(d.get("content", "")):
                ad = (o.get("name") or "").lower()
                ds = (o.get("data") or [{}])[0].get("data") or []
                if "yıllık değişim oranları" in ad and len(ds) > 5 and "tüfe yıllık" not in ad:
                    g["labels"], g["yoy"] = [str(x).replace("Sigort ", "Sigorta ") for x in o.get("labels", [])], ds
                elif "yıllık etki" in ad or "yıllık katkı" in ad:
                    g["yoyK"] = ds
                elif "aylık değişim oranları" in ad and len(ds) > 5:
                    g["mom"] = ds
                elif "aylık etki" in ad or "aylık katkı" in ad:
                    g["momK"] = ds
            if g.get("labels") and g.get("yoy"):
                gruplar[ay] = g
        log(f"   TÜİK {baslik} {ay}: bülten {pid}")
        # önceki bültenler: eksik ay kaldıysa ve sınırın içindeyse
        for p in d.get("previousPresses") or []:
            pa = ay_kodu(p.get("period"))
            ppid = str(p.get("url", "")).rstrip("/").split("/")[-1]
            if not pa or not ppid.isdigit() or pa < sinir:
                continue
            eksik = pa not in veri or veri[pa].get("mom") is None or (kirilim and pa not in gruplar)
            if eksik and ppid not in gorulen:
                kuyruk.append(ppid)
        time.sleep(0.4)
    aylar = sorted(a for a in veri if veri[a].get("yoy") is not None)
    return {"months": aylar, **{k: [veri[a].get(k) for a in aylar] for k in ("mom", "ytd", "yoy", "avg12")},
            "press": {a: bultenler[a] for a in aylar if a in bultenler},
            **({"groups": {a: gruplar[a] for a in sorted(gruplar)}} if kirilim else {}),
            "updated": simdi(), "source": f"TÜİK, {baslik}"}


# ------------------------------------------------------------------ EVDS
BEKLENTI = {
    "pk_yilsonu": "TP.PKAUO.S01.D.U",     # Piyasa Katılımcıları Anketi: cari yıl sonu TÜFE beklentisi
    "pk_12ay": "TP.PKAUO.S01.E.U",        # 12 ay sonrası yıllık TÜFE beklentisi
    "pk_24ay": "TP.PKAUO.S01.F.U",
    "pk_gelecek_yilsonu": "TP.PKAUO.S01.I.U",
    "reel_12ay": "TP.ENFBEK.IYA12ENF",    # reel sektör 12 ay sonrası
    "hh_12ay": "TP.ENFBEK.HBA12ENF",      # hanehalkı 12 ay sonrası
    "pk_12ay_enfbek": "TP.ENFBEK.PKA12ENF",
}


def evds_aylik(anahtar, kodlar, bas):
    s = oturum()
    s.headers.update({"key": anahtar})
    out, bit = {}, dt.date.today()
    while bas <= bit:
        son = min(bit, bas + dt.timedelta(days=364 * 3))
        url = EVDS + f"series={'-'.join(kodlar)}&startDate={bas:%d-%m-%Y}&endDate={son:%d-%m-%Y}&type=json"
        r = s.get(url, timeout=120, allow_redirects=False)
        if r.status_code == 403:
            raise RuntimeError("EVDS anahtarı reddedildi (EVDS_API_KEY)")
        r.raise_for_status()
        for it in r.json().get("items", []):
            mm = re.match(r"^(\d{4})-(\d{1,2})$", it.get("Tarih", ""))
            if not mm:
                continue
            ay = f"{mm.group(1)}-{int(mm.group(2)):02d}"
            for c in kodlar:
                v = it.get(c.replace(".", "_"))
                if v not in (None, "", "ND"):
                    try:
                        out.setdefault(ay, {})[c] = float(v)
                    except (TypeError, ValueError):
                        pass
        bas = son + dt.timedelta(days=1)
        time.sleep(0.3)
    return out


def beklentiler(anahtar):
    ham = evds_aylik(anahtar, list(BEKLENTI.values()), dt.date(2018, 1, 1))
    aylar = sorted(ham)
    return {"months": aylar, **{k: [ham[a].get(c) for a in aylar] for k, c in BEKLENTI.items()},
            "codes": BEKLENTI, "updated": simdi(), "source": "TCMB EVDS (bie_pkauo, bie_enfbek)"}


def bist_repo(anahtar):
    """Borsa İstanbul Repo Pazarı gecelik: ağırlıklı ortalama faiz ve işlem hacmi (EVDS bie_onrepofbap)."""
    s = oturum()
    s.headers.update({"key": anahtar})
    kod = ["TP.AOFOBAP", "TP.IHBAP"]
    out, bas, bit = {}, dt.date(2019, 1, 1), dt.date.today()
    while bas <= bit:
        son = min(bit, bas + dt.timedelta(days=364))
        r = s.get(EVDS + f"series={'-'.join(kod)}&startDate={bas:%d-%m-%Y}&endDate={son:%d-%m-%Y}&type=json", timeout=120, allow_redirects=False)
        if r.status_code == 403:
            raise RuntimeError("EVDS anahtarı reddedildi (EVDS_API_KEY)")
        r.raise_for_status()
        for it in r.json().get("items", []):
            mm = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", it.get("Tarih", ""))
            if not mm:
                continue
            g = f"{mm.group(3)}-{mm.group(2)}-{mm.group(1)}"
            for c in kod:
                v = it.get(c.replace(".", "_"))
                if v not in (None, "", "ND"):
                    out.setdefault(g, {})[c] = float(v)
        bas = son + dt.timedelta(days=1)
        time.sleep(0.3)
    tarih = sorted(t for t in out if "TP.AOFOBAP" in out[t])
    return {"dates": tarih, "rate": [out[t]["TP.AOFOBAP"] for t in tarih], "vol_tl": [out[t].get("TP.IHBAP") for t in tarih],
            "updated": simdi(), "source": "Borsa İstanbul Repo Pazarı O/N (TCMB EVDS, bie_onrepofbap)"}


# ------------------------------------------------------------------ TCMB hedef ve Enflasyon Raporu
def tablo_satirlari(html):
    out = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", html, re.I):
        out.append([htmlmod.unescape(re.sub(r"<[^>]+>", "", h)).replace("\xa0", " ").strip()
                    for h in re.findall(r"<t[hd][^>]*>([\s\S]*?)</t[hd]>", tr, re.I)])
    return out


def tcmb_hedefler(s):
    url = TCMB + "/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Temel+Faaliyetler/Para+Politikasi/Fiyat+Istikrari+ve+Enflasyon/Enflasyonun+Hedefleri"
    r = s.get(url, timeout=60)
    r.raise_for_status()
    out = []
    for h in tablo_satirlari(r.text):
        if len(h) >= 3 and re.fullmatch(r"\d{4}", h[0]):
            out.append({"yil": int(h[0]), "hedef": sayi(h[1]), "gercek": sayi(h[2])})
    if not out:
        raise RuntimeError("TCMB hedef tablosu okunamadı")
    return {"rows": out, "url": url, "updated": simdi()}


def pdf_metin(veri):
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(veri)).pages)


def rapor_tahmin(metin):
    t = re.sub(r"\s+", " ", metin)
    t = re.sub(r"(?<=\d) (?=\d)", "", t)                       # "2 8" -> "28" (PDF boşlukları)
    t = re.sub(r"(?<=\d) , ?(?=\d)", ",", t)
    tah = {}
    for m in re.finditer(r"(20\d\d) yıl sonunda (?:ise )?yüzde ?(\d+(?:,\d+)?)", t):
        tah.setdefault(m.group(1), sayi(m.group(2)))
    ara = {}
    m = re.search(r"Ara hedefler,? ((?:20\d\d,? (?:ve )?)+)yılları için sırasıyla ((?:yüzde ?\d+(?:,\d+)?,? (?:ve )?)+)", t)
    if m:
        yillar = re.findall(r"20\d\d", m.group(1))
        oranlar = [sayi(x) for x in re.findall(r"yüzde ?(\d+(?:,\d+)?)", m.group(2))]
        ara = dict(zip(yillar, oranlar))
    return tah, ara


def enflasyon_raporu(s):
    """En güncel Enflasyon Raporu: '3. Orta Vadeli Öngörüler' PDF'inden yıl sonu tahminleri ve ara hedefler."""
    taban = TCMB + "/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Yayinlar/Raporlar/Enflasyon+Raporu/"
    for yil in (dt.date.today().year, dt.date.today().year - 1):
        r = s.get(taban + str(yil), timeout=60)
        if r.status_code != 200:
            continue
        linkler = re.findall(r'href="([^"]*Enflasyon\+Raporu\+%d\+-\+(IV|I{1,3})/?)"' % yil, r.text)
        sira = {"I": 1, "II": 2, "III": 3, "IV": 4}
        for href, no in sorted(set(linkler), key=lambda x: -sira.get(x[1], 0)):   # en yeniden eskiye; henüz yayımlanmamışı atla
            sayfa_url = href if href.startswith("http") else TCMB + href
            p = s.get(sayfa_url, timeout=60)
            if p.status_code != 200:
                continue
            baslik = re.search(r"<title>\s*TCMB - ([^<]+)</title>", p.text)
            m = re.search(r"Orta Vadeli [ÖöOo]ng[öo]r[üu]ler[\s\S]{0,800}?href=\"([^\"]+\.pdf[^\"]*)\"", p.text)
            if not m:
                log(f"   {yil}-{no}: Orta Vadeli Öngörüler PDF'i yok (henüz yayımlanmamış olabilir)")
                continue
            pdf_url = htmlmod.unescape(m.group(1))
            pdf_url = pdf_url if pdf_url.startswith("http") else TCMB + pdf_url
            pdf = s.get(pdf_url, timeout=120)
            pdf.raise_for_status()
            tah, ara = rapor_tahmin(pdf_metin(pdf.content))
            if not tah:
                log(f"   {yil}-{no}: tahmin cümlesi bulunamadı")
                continue
            return {"ad": htmlmod.unescape(baslik.group(1)).strip() if baslik else f"Enflasyon Raporu {yil} - {no}",
                    "url": sayfa_url, "pdf": pdf_url, "tahmin": tah, "ara_hedef": ara, "updated": simdi(), "otomatik": True}
    raise RuntimeError("Enflasyon Raporu sayfası bulunamadı")


# ------------------------------------------------------------------ Borsa İstanbul TLREF / TLREFK
def bist_oran(s, tip):
    r = s.get(f"https://www.borsaistanbul.com/bist-tlrefk.php?op=fetchTlrefkData&dataType={tip}-history&day=7000",
              headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"https://www.borsaistanbul.com/endeksler/{tip}"}, timeout=90)
    r.raise_for_status()
    j = r.json()
    if j.get("status") != "success":
        raise RuntimeError(f"BIST {tip}: {j.get('status')}")
    seri = {}
    for x in j.get("data") or []:
        v = sayi(x.get("clval"))
        if x.get("date") and v is not None:
            seri[x["date"][:10]] = v
    hacim = {}
    try:                                                   # tarihsel dosya: işlem hacmi, adet, aktif üye
        hacim = bist_tarihsel(s, tip)
        for t, h in hacim.items():
            seri.setdefault(t, h["rate"])
    except Exception as e:
        log(f"   {tip.upper()} tarihsel dosya okunamadı ({type(e).__name__}: {e}); yalnızca oran")
    tarih = sorted(t for t in seri if seri[t] is not None)
    if not tarih:
        raise RuntimeError(f"BIST {tip}: veri yok")
    return {"dates": tarih, "rate": [seri[t] for t in tarih],
            "vol_tl": [hacim.get(t, {}).get("vol") for t in tarih], "count": [hacim.get(t, {}).get("n") for t in tarih],
            "members": [hacim.get(t, {}).get("uye") for t in tarih], "updated": simdi(),
            "source": f"Borsa İstanbul, {tip.upper()} (oran ve tarihsel işlem hacmi)"}


def bist_tarihsel(s, tip):
    """/datum/TLREFORANI_D.zip ya da TLREFKORANI_D.zip: UTF-16 CSV; TARIH;AD;..;DEGER;REPO AOF;ISLEM HACMI;ISLEM ADEDI;AKTIF UYE;..."""
    import zipfile
    r = s.get(f"https://www.borsaistanbul.com/datum/{tip.upper()}ORANI_D.zip", timeout=90,
              headers={"Referer": f"https://www.borsaistanbul.com/endeksler/{tip}"})
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    ham = z.read(z.namelist()[0])
    metin = ham.decode("utf-16") if ham[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in ham[:200] else ham.decode("utf-8", "ignore")
    tam = lambda x: float(x.replace(",", "")) if x and x.strip() not in ("", "-") else None
    out = {}
    for satir in metin.splitlines():
        h = satir.split(";")
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})$", h[0].strip()) if h else None
        if not m or len(h) < 10:
            continue
        try:
            out[f"{m.group(3)}-{m.group(2)}-{m.group(1)}"] = {"rate": tam(h[5]), "vol": tam(h[7]), "n": tam(h[8]), "uye": tam(h[9])}
        except ValueError:
            continue
    log(f"   {tip.upper()} tarihsel: {len(out)} gün, son {max(out) if out else '-'}")
    return out


# ------------------------------------------------------------------ ana akış
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site")
    ap.add_argument("--sadece", default="", help="virgülle: tufe,ufe,beklenti,hedef,rapor,tlref,tlrefk,bistrepo")
    a = ap.parse_args()
    cikti = os.path.join(a.site, "makro")
    yol = os.path.join(cikti, "data", "makro.json")
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    try:
        D = json.load(open(yol, encoding="utf-8"))
        log("Önceki makro verisi yüklendi")
    except Exception:
        D = {}
    s = oturum()
    anahtar = os.environ.get("EVDS_API_KEY", "")
    isler = [
        ("tufe", lambda: tuik_seri(s, "Tüketici Fiyat Endeksi", D.get("tufe", {}), kirilim=True)),
        ("ufe", lambda: tuik_seri(s, "Yurt İçi Üretici Fiyat Endeksi", D.get("ufe", {}))),
        ("beklenti", lambda: beklentiler(anahtar) if anahtar else (_ for _ in ()).throw(RuntimeError("EVDS_API_KEY yok"))),
        ("hedef", lambda: tcmb_hedefler(s)),
        ("rapor", lambda: enflasyon_raporu(s)),
        ("tlref", lambda: bist_oran(s, "tlref")),
        ("tlrefk", lambda: bist_oran(s, "tlrefk")),
        ("bistrepo", lambda: bist_repo(anahtar) if anahtar else (_ for _ in ()).throw(RuntimeError("EVDS_API_KEY yok"))),
    ]
    secim = set(x for x in a.sadece.split(",") if x)
    sorun = []
    for ad, fn in isler:
        if secim and ad not in secim:
            continue
        try:
            log(f"== {ad}")
            D[ad] = fn()
        except Exception as e:
            log(f"HATA {ad}: {type(e).__name__}: {e} — önceki veri korunuyor")
            sorun.append(ad)
    # rapor otomatik okunamadıysa repodaki elle girilmiş değer
    if not D.get("rapor"):
        try:
            D["rapor"] = json.load(open(os.path.join(KOK, "tcmb_tahmin.json"), encoding="utf-8"))
            log("Enflasyon Raporu tahmini: elle girilen değer (makro/tcmb_tahmin.json)")
        except Exception:
            pass
    D.pop("tpp", None)
    try:                                                   # Web TÜFE: webtufe.com verisi (makro/webtufe.json)
        D["webtufe"] = json.load(open(os.path.join(KOK, "webtufe.json"), encoding="utf-8"))
    except Exception as e:
        log(f"Web TÜFE dosyası okunamadı: {e}")
    D["updated"] = simdi()
    D["failed"] = sorun
    json.dump(D, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(cikti, "index.html"), "w", encoding="utf-8").write(open(os.path.join(KOK, "sayfa.html"), encoding="utf-8").read())
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(KOK), "ortak"))
        from durum import yaz
        if D.get("tufe", {}).get("months"):
            yaz(a.site, "tufe", D["tufe"]["months"][-1])
        son_p = [D[k]["dates"][-1] for k in ("tlref", "bistrepo") if D.get(k, {}).get("dates")]
        if son_p:
            yaz(a.site, "piyasa", max(son_p))
    except Exception as e:
        log(f"durum.json yazılamadı: {e}")
    log(f"TAMAM — sorunlu: {', '.join(sorun) or 'yok'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
