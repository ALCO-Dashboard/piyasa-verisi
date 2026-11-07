"""Makro ve Piyasa → Makro Veriler: Büyüme, İstihdam, Üretim Endeksleri, Dış Ticaret ve Dış Denge, Bütçe.

Kaynaklar
  TCMB EVDS (EVDS_API_KEY): GSYH (harcama, üretim, gelir yöntemi; zincirlenmiş hacim, MEA, cari fiyat), ödemeler dengesi,
      dış ticaret (ISIC, BEC), merkezi yönetim bütçe gelir/giderleri, imalat sanayi kapasite kullanım oranı, USD/TRY.
  TÜİK Veri Portalı (bültenlerin Excel tabloları): sanayi, hizmet, inşaat ve ticaret satış hacim endeksleri; işgücü
      (MEA temel göstergeler, 15-24 yaş, atıl işgücü); dış ticarette en çok ihracat/ithalat yapılan 20 ülke.
      EVDS'de olmayan ya da EVDS'ye geç düşen seriler buradan alınır. TÜİK aynı anda çok dosya indirmeye izin vermediği
      için indirmeler arasında bekleme var.

Çıktı: site/makro/data/ekonomi.json
Kullanım: python ekonomi/guncelle.py --site site
"""
import argparse
import datetime as dt
import importlib.util
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
AYLAR = ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"]

# ------------------------------------------------------------------ EVDS seri listeleri
AYLIK = {
    # dış ticaret (TÜİK, genel ticaret sistemi, bin USD)
    "ihr": "TP.IHRISICREV4.TT", "ith": "TP.ITHISICREV4.TT",
    "ihr_sermaye": "TP.IHRACATBEC.1", "ihr_ara": "TP.IHRACATBEC.2", "ihr_tuketim": "TP.IHRACATBEC.3", "ihr_diger": "TP.IHRACATBEC.4",
    "ith_sermaye": "TP.ITHALATBEC.1", "ith_ara": "TP.ITHALATBEC.2", "ith_tuketim": "TP.ITHALATBEC.3", "ith_diger": "TP.ITHALATBEC.4",
    # ödemeler dengesi (milyon USD)
    "cari": "TP.ODANA6.Q01", "od_ihr": "TP.ODANA6.Q02", "od_ith": "TP.ODANA6.Q03", "mal": "TP.ODANA6.Q04",
    "hiz_gel": "TP.ODANA6.Q05", "hiz_gid": "TP.ODANA6.Q06", "bir_gel": "TP.ODANA6.Q08", "bir_gid": "TP.ODANA6.Q09",
    "finans": "TP.ODANA6.Q13", "dyy_var": "TP.ODANA6.Q14", "dyy_yuk": "TP.ODANA6.Q15", "port_var": "TP.ODANA6.Q16",
    "port_yuk": "TP.ODANA6.Q17", "port_hisse": "TP.ODANA6.Q18", "port_borc": "TP.ODANA6.Q19", "diger_yuk": "TP.ODANA6.Q25",
    "bnk_yuk": "TP.ODANA6.Q28", "net_hata": "TP.ODANA6.Q31", "rezerv": "TP.ODANA6.Q33",
    "hizmet": "TP.ODEAYRSUNUM6.Q20", "birincil": "TP.ODEAYRSUNUM6.Q68", "ikincil": "TP.ODEAYRSUNUM6.Q92",
    "seyahat_gel": "TP.ODEAYRSUNUM6.Q42", "seyahat_gid": "TP.ODEAYRSUNUM6.Q43", "tasima_gel": "TP.ODEAYRSUNUM6.Q30", "tasima_gid": "TP.ODEAYRSUNUM6.Q31",
    "altin_ihr": "TP.ODEAYRSUNUM6.Q18", "altin_ith": "TP.ODEAYRSUNUM6.Q19",
    "cari_altinh": "TP.HARICCARIACIK.K8", "cari_enerjih": "TP.HARICCARIACIK.K9", "cari_altin_enerjih": "TP.HARICCARIACIK.K10",
    # merkezi yönetim bütçesi (bin TL)
    "b_gelir": "TP.KB.GEL001", "b_vergi": "TP.KB.GEL003", "b_gv": "TP.KB.GEL005", "b_kv": "TP.KB.GEL010", "b_mulkiyet": "TP.KB.GEL014",
    "b_kdv_ic": "TP.KB.GEL018", "b_otv": "TP.KB.GEL021", "b_otv_petrol": "TP.KB.GEL022", "b_otv_motorlu": "TP.KB.GEL023",
    "b_otv_alkol": "TP.KB.GEL024", "b_otv_tutun": "TP.KB.GEL025", "b_bsmv": "TP.KB.GEL028", "b_dis_ticaret": "TP.KB.GEL031",
    "b_kdv_ithal": "TP.KB.GEL033", "b_damga": "TP.KB.GEL035", "b_harc": "TP.KB.GEL036",
    "b_tesebbus": "TP.KB.GEL038", "b_faiz_pay": "TP.KB.GEL061", "b_sermaye_gel": "TP.KB.GEL079",
    "b_gider": "TP.KB.GID001", "b_faizdisi_gider": "TP.KB.GID002", "b_personel": "TP.KB.GID003", "b_sgk_prim": "TP.KB.GID008",
    "b_mal_hizmet": "TP.KB.GID014", "b_cari_transfer": "TP.KB.GID026", "b_hazine_yardim": "TP.KB.GID033", "b_vergi_pay": "TP.KB.GID096",
    "b_sermaye_gid": "TP.KB.GID110", "b_sermaye_transfer": "TP.KB.GID116", "b_borc_verme": "TP.KB.GID131",
    "b_faiz": "TP.KB.GID152", "b_faiz_ic": "TP.KB.GID153", "b_faiz_dis": "TP.KB.GID160", "b_faiz_kira": "TP.KB.GID163",
    # kapasite kullanım
    "kko": "TP.KKO.MA",
}
CEYREK = {
    # MEA zincirlenmiş hacim endeksi (harcama)
    "mea": "TP.GSYIH30.HY.B1GQ", "mea_hh": "TP.GSYIH30.HY.P311", "mea_devlet": "TP.GSYIH30.HY.P32", "mea_yatirim": "TP.GSYIH30.HY.P51G",
    "mea_ihr": "TP.GSYIH30.HY.P6", "mea_ith": "TP.GSYIH30.HY.P7",
    # harcama yöntemi, zincirlenmiş hacim (bin TL)
    "h_gsyh": "TP.GSYIH20.CY.B1GQ", "h_hh": "TP.GSYIH20.CY.P311", "h_kamuoz": "TP.GSYIH20.CY.P312", "h_devlet": "TP.GSYIH20.CY.P32",
    "h_yatirim": "TP.GSYIH20.CY.P51G", "h_ihr": "TP.GSYIH20.CY.P6", "h_ith": "TP.GSYIH20.CY.P7",
    # harcama yöntemi, cari fiyat (bin TL)
    "c_gsyh": "TP.GSYIH20.BY.B1GQ", "c_hh": "TP.GSYIH20.BY.P311", "c_devlet": "TP.GSYIH20.BY.P32", "c_yatirim": "TP.GSYIH20.BY.P51G",
    "c_stok": "TP.GSYIH20.BY.P52", "c_ihr": "TP.GSYIH20.BY.P6", "c_ith": "TP.GSYIH20.BY.P7",
    # üretim yöntemi (A10), zincirlenmiş hacim ve cari fiyat (bin TL)
    "u_gsyh": "TP.GSYIH40.IFC.B1GQ", "u_tarim": "TP.GSYIH40.IFC.A", "u_sanayi": "TP.GSYIH40.IFC.BTE", "u_imalat": "TP.GSYIH40.IFC.C",
    "u_insaat": "TP.GSYIH40.IFC.F", "u_ticaret": "TP.GSYIH40.IFC.GTI", "u_bilgi": "TP.GSYIH40.IFC.J", "u_finans": "TP.GSYIH40.IFC.K",
    "u_gayrimenkul": "TP.GSYIH40.IFC.L", "u_mesleki": "TP.GSYIH40.IFC.MN", "u_kamu": "TP.GSYIH40.IFC.OTQ", "u_diger": "TP.GSYIH40.IFC.RTU",
    "u_vergi": "TP.GSYIH40.IFC.D21X31",
    "uc_gsyh": "TP.GSYIH040.IFK.B1GQ", "uc_tarim": "TP.GSYIH040.IFK.A", "uc_sanayi": "TP.GSYIH040.IFK.BTE", "uc_imalat": "TP.GSYIH040.IFK.C",
    "uc_insaat": "TP.GSYIH040.IFK.F", "uc_ticaret": "TP.GSYIH040.IFK.GTI", "uc_bilgi": "TP.GSYIH040.IFK.J", "uc_finans": "TP.GSYIH040.IFK.K",
    "uc_gayrimenkul": "TP.GSYIH040.IFK.L", "uc_mesleki": "TP.GSYIH040.IFK.MN", "uc_kamu": "TP.GSYIH040.IFK.OTQ", "uc_diger": "TP.GSYIH040.IFK.RTU",
    "uc_vergi": "TP.GSYIH040.IFK.D21X31",
    # gelir yöntemi, cari fiyat (bin TL)
    "g_gsyh": "TP.GSYIH30.AY.B1GQ", "g_isgucu": "TP.GSYIH30.AY.D1", "g_uretim_vergi": "TP.GSYIH30.AY.D29X39", "g_brut_artik": "TP.GSYIH30.AY.B2A3G",
    "g_sabit_sermaye": "TP.GSYIH30.AY.P51C", "g_net_artik": "TP.GSYIH30.AY.B2N3N", "g_urun_vergi": "TP.GSYIH30.AY.D21X31",
}
YILLIK = {"kb_usd": "TP.GSYHKB.CF.USD", "kb_tl": "TP.GSYHKB.CF.TL"}

# ------------------------------------------------------------------ TÜİK tabloları: (bülten, tablo adı deseni, anahtar)
TUIK_TABLO = [
    ("Sanayi Üretim Endeksi", r"^Sanayi Üretim Endeksi ve Değişim", "sanayi"),
    ("Hizmet Üretim Endeksi", r"^Hizmet Üretim Endeksi", "hizmet"),
    ("İnşaat Üretim Endeksi", r"^İnşaat Üretim Endeksi", "insaat"),
    ("Ticaret Satış Hacim Endeksi", r"^Ticaret Satış Hacim Endeksi", "ticaret"),
    ("İşgücü İstatistikleri", r"^Mevsim etkisinden arındırılmış temel işgücü göstergeleri \(15\+", "isgucu"),
    ("İşgücü İstatistikleri", r"^Mevsim etkisinden arındırılmış temel işgücü göstergeleri \(15-24", "genc"),
    ("İşgücü İstatistikleri", r"^Mevsim ve takvim etkilerinden arındırılmış işgücüne ilişkin tamamlayıcı", "atil"),
    ("Dış Ticaret İstatistikleri", r"en çok ihracat ve ithalat yapılan 20 ülke", "ulke"),
]
# üretim endekslerinde tutulacak bloklar (başlığın ilk satırına göre)
BLOK = {
    "sanayi": r"^(Toplam|[BCD]-|ARM|DLT|DZT|ENJ|SEM)",
    "hizmet": r"^(H-N|[HIJLMN] -)",
    "insaat": r"^(Toplam|4[123]-)",
    "ticaret": r"^(G -|4[567] -)",
}
BAS_YIL = 2015


def log(*a):
    print(*a, flush=True)


def simdi():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ EVDS
def evds_tarih(t):
    t = str(t or "")
    m = re.match(r"^(\d{4})-(\d{1,2})$", t)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{4})-Q([1-4])$", t)
    if m:
        return f"{m.group(1)}-Q{m.group(2)}"
    if re.match(r"^\d{4}$", t):
        return t
    m = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", t)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def evds(anahtar, kodlar, bas, bit, yil_parca=4):
    """{tarih: {kod: değer}}"""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "key": anahtar})
    out = {}
    for i in range(0, len(kodlar), 20):
        grup, b = kodlar[i:i + 20], bas
        while b <= bit:
            son = min(bit, dt.date(b.year + yil_parca, 1, 1) - dt.timedelta(days=1))
            url = EVDS + f"series={'-'.join(grup)}&startDate={b:%d-%m-%Y}&endDate={son:%d-%m-%Y}&type=json"
            for deneme in range(4):
                try:
                    r = s.get(url, timeout=120, allow_redirects=False)
                    if r.status_code == 403:
                        raise RuntimeError("EVDS anahtarı reddedildi (EVDS_API_KEY)")
                    r.raise_for_status()
                    items = r.json().get("items", [])
                    break
                except RuntimeError:
                    raise
                except Exception as e:
                    if deneme == 3:
                        raise
                    log(f"   EVDS yeniden deneniyor ({type(e).__name__})")
                    time.sleep(5 * (deneme + 1))
            for it in items:
                t = evds_tarih(it.get("Tarih"))
                if not t:
                    continue
                for c in grup:
                    v = it.get(c.replace(".", "_"))
                    if v not in (None, "", "ND"):
                        try:
                            out.setdefault(t, {})[c] = float(v)
                        except (TypeError, ValueError):
                            pass
            b = son + dt.timedelta(days=1)
            time.sleep(0.3)
    return out


def tablo(ham, harita, tarihler=None):
    t = tarihler or sorted(ham)
    return {"dates": t, **{k: [ham.get(d, {}).get(c) for d in t] for k, c in harita.items()}}


def ceyrek_kur(anahtar):
    """Çeyreklik ve aylık ortalama USD/TRY (TCMB döviz alış), günlük seriden."""
    G = evds(anahtar, ["TP.DK.USD.A.YTL"], dt.date(BAS_YIL - 1, 1, 1), dt.date.today(), yil_parca=1)
    q, m = {}, {}
    for d, v in G.items():
        x = v.get("TP.DK.USD.A.YTL")
        if x and len(d) == 10:
            y, a = int(d[:4]), int(d[5:7])
            q.setdefault(f"{y}-Q{(a - 1) // 3 + 1}", []).append(x)
            m.setdefault(d[:7], []).append(x)
    return {k: sum(v) / len(v) for k, v in q.items()}, {k: sum(v) / len(v) for k, v in m.items()}


# ------------------------------------------------------------------ TÜİK
def oku_xls(icerik):
    """BIFF .xls → satır listesi (xlrd); .xlsx gelirse openpyxl."""
    if icerik[:4] == b"PK\x03\x04":
        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(icerik), data_only=True, read_only=True).worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    import xlrd
    sh = xlrd.open_workbook(file_contents=icerik).sheet_by_index(0)
    return [[sh.cell_value(i, j) if sh.cell_value(i, j) != "" else None for j in range(sh.ncols)] for i in range(sh.nrows)]


def tuik_indir(s, gerekli, onceki=None, guncel=None):
    """{anahtar: (bülten bilgisi, satırlar)}. Bülten numarası kayıtlı veriyle aynıysa dosya indirilmez (guncel kümesine eklenir)."""
    onceki = onceki or {}
    H = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
    P = lambda v: json.loads(v or "[]") if isinstance(v, str) else (v or [])
    liste = s.get(f"{TUIK}/api/tr/press", headers=H, timeout=60).json()["data"]
    bultenler, out = {}, {}
    for baslik, desen, anahtar in TUIK_TABLO:
        if anahtar not in gerekli:
            continue
        try:
            if baslik not in bultenler:
                x = next(b for b in liste if b.get("title") == baslik)
                bultenler[baslik] = s.get(f"{TUIK}/api/tr/press/{x['id']}", headers=H, timeout=60).json()["data"]
            d = bultenler[baslik]
            if str((onceki.get(anahtar) or {}).get("kaynak", {}).get("no")) == str(d.get("id")):
                guncel.add(anahtar)
                log(f"   TÜİK {anahtar}: {baslik} · {d.get('period')} · yeni bülten yok, kayıtlı veri kullanılıyor")
                continue
            t = next(t for t in P(d.get("tables")) if t.get("type") == "xls" and re.search(desen, t.get("title", ""), re.I))
            for deneme in range(4):
                time.sleep([8, 20, 40, 60][deneme])         # TÜİK: art arda indirmede bekleme sayfası döndürüyor
                r = s.get(TUIK + t["url"], timeout=180)
                if r.ok and not r.content[:200].lstrip().startswith(b"<"):
                    break
            else:
                ic = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.content[:3000].decode("utf-8", "replace")))[:200]
                raise RuntimeError(f"dosya indirilemedi (HTTP {r.status_code}, {r.headers.get('content-type')}): {ic}")
            out[anahtar] = ({"bulten": baslik, "donem": d.get("period"), "no": d.get("id"), "tablo": t.get("title")}, oku_xls(r.content))
            log(f"   TÜİK {anahtar}: {baslik} · {d.get('period')} · {len(out[anahtar][1])} satır")
        except Exception as e:
            log(f"HATA TÜİK {anahtar}: {type(e).__name__}: {e}")
    return out


def sayi(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return round(float(v), 4)
    try:
        return round(float(str(v).replace(",", ".")), 4)
    except (TypeError, ValueError):
        return None


def ilk_satir(v):
    return re.split(r"\s*\n\s*", str(v or "").strip())[0].strip()


def uretim_endeksi(R, blok_deseni):
    """Üretim/hacim endeksi tablosu → {dates, bloklar: [{ad, ham, takvim, yoy, mea, mom}]}"""
    h = next(i for i, r in enumerate(R) if any(str(x or "").strip().startswith("Arındırılmamış") for x in r))
    t = max(i for i in range(h) if any(isinstance(x, str) and x.strip() for x in R[i][2:]))
    if t == h - 1 and not any(str(x or "").strip() for x in R[t][2:] if not str(x or "").startswith(("Arındırıl", "Takvim", "Mevsim"))):
        t -= 1
    basl = [(j, ilk_satir(x)) for j, x in enumerate(R[t]) if j >= 2 and isinstance(x, str) and x.strip()]
    bas = next(i for i in range(h + 1, len(R)) if re.match(r"^\s*\d{1,2}\s*$", str(R[i][1] or "").split(".")[0]))
    tarih, satir, yil = [], [], None
    for r in R[bas:]:
        y = str(r[0] or "").strip().split(".")[0]
        if re.match(r"^\d{4}$", y):
            yil = int(y)
        a = str(r[1] or "").strip().split(".")[0]
        if not yil or not re.match(r"^\d{1,2}$", a):
            continue
        if yil >= BAS_YIL:
            tarih.append(f"{yil}-{int(a):02d}")
            satir.append(r)
    bloklar = []
    for k, (j, ad) in enumerate(basl):
        if not re.search(blok_deseni, ad):
            continue
        son = basl[k + 1][0] if k + 1 < len(basl) else len(R[h])
        alt = {c: str(R[h][c] or "") for c in range(j, son)}
        un = next((c for c, v in alt.items() if v.startswith("Arındırılmamış")), None)
        tk = next((c for c, v in alt.items() if v.startswith("Takvim")), None)
        me = next((c for c, v in alt.items() if v.startswith("Mevsim")), None)
        col = lambda c: [sayi(r[c]) if c is not None and c < len(r) else None for r in satir]
        bloklar.append({"ad": ad, "ham": col(un), "takvim": col(tk), "yoy": col(tk + 1 if tk is not None else None),
                        "mea": col(me), "mom": col(me + 1 if me is not None else None)})
    return {"dates": tarih, "bloklar": bloklar}


def ay_no(v):
    w = str(v or "").strip().split(" ")[0].lower()
    return AYLAR.index(w) + 1 if w in AYLAR else None


def isgucu_tablo(R, anahtarlar):
    """Yıl (sütun 0, devam eder) / ay adı (sütun 1) / değerler (sütun 2…) → {dates, anahtar: [...]} (Toplam bloğu)."""
    tarih, veri, yil = [], {k: [] for k in anahtarlar}, None
    for r in R:
        y = str(r[0] or "").strip().split(".")[0]
        if re.match(r"^\d{4}$", y):
            yil = int(y)
        a = ay_no(r[1] if len(r) > 1 else None)
        if not yil or not a:
            continue
        if yil >= BAS_YIL and f"{yil}-{a:02d}" not in tarih:
            tarih.append(f"{yil}-{a:02d}")
            for i, k in enumerate(anahtarlar):
                veri[k].append(sayi(r[2 + i]) if 2 + i < len(r) else None)
    return {"dates": tarih, **veri}


def ulke_tablo(R):
    """En çok ihracat/ithalat yapılan 20 ülke: {ay, ytd, ihr: [...], ith: [...]} — değerler bin USD."""
    ay_ad = next((str(x).strip() for r in R[:6] for x in r if isinstance(x, str) and ay_no(x) and "-" not in x), None)
    out, bolum = {"ay": ay_ad, "ihr": [], "ith": []}, None
    for r in R:
        b = str(r[1] or "").strip()
        if b.startswith("İhracat"):
            bolum = "ihr"
            continue
        if b.startswith("İthalat"):
            bolum = "ith"
            continue
        if not bolum or not re.match(r"^\d+-?$", str(r[0] or "").strip().split(".")[0].rstrip("-") or "x"):
            continue
        ad = re.split(r"\s+-\s+", b)[0].strip()
        out[bolum].append({"ad": ad, "onceki": sayi(r[2]), "deger": sayi(r[5]), "pay": sayi(r[6]), "degisim": sayi(r[7]),
                           "ytd_onceki": sayi(r[9]), "ytd": sayi(r[12]) if len(r) > 12 else None, "ytd_pay": sayi(r[13]) if len(r) > 13 else None})
    return out


# ------------------------------------------------------------------ ana akış
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site")
    ap.add_argument("--tuik-yerel", help="test: TÜİK tablolarını bu klasördeki <anahtar>.xlsx dosyalarından oku")
    a = ap.parse_args()
    yol = os.path.join(a.site, "makro", "data", "ekonomi.json")
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    try:
        D = json.load(open(yol, encoding="utf-8"))
    except Exception:
        D = {}
    sorun = []
    anahtar = os.environ.get("EVDS_API_KEY")
    bugun = dt.date.today()
    if anahtar:
        for ad, fn in (
            ("aylik", lambda: tablo(evds(anahtar, list(AYLIK.values()), dt.date(BAS_YIL, 1, 1), bugun), AYLIK)),
            ("ceyrek", lambda: tablo(evds(anahtar, list(CEYREK.values()), dt.date(BAS_YIL - 1, 1, 1), bugun), CEYREK)),
            ("yillik", lambda: tablo(evds(anahtar, list(YILLIK.values()), dt.date(BAS_YIL, 1, 1), bugun, yil_parca=20), YILLIK)),
        ):
            try:
                D[ad] = fn()
                son = {k: next((D[ad]["dates"][i] for i in range(len(v) - 1, -1, -1) if v[i] is not None), None)
                       for k, v in D[ad].items() if k != "dates"}
                log(f"   EVDS {ad}: {len(D[ad]['dates'])} dönem; son veri " + ", ".join(sorted({x for x in son.values() if x}, reverse=True)[:3]))
                eksik = [k for k, v in son.items() if v is None]
                if eksik:
                    log(f"   EVDS {ad}: veri gelmeyen seriler: {', '.join(eksik)}")
            except Exception as e:
                log(f"HATA EVDS {ad}: {type(e).__name__}: {e} — önceki veri korunuyor")
                sorun.append(ad)
        try:
            q, m = ceyrek_kur(anahtar)
            D["kur"] = {"q": {k: round(v, 4) for k, v in sorted(q.items())}, "m": {k: round(v, 4) for k, v in sorted(m.items())}}
        except Exception as e:
            log(f"HATA EVDS kur: {type(e).__name__}: {e}")
            sorun.append("kur")
    else:
        log("EVDS_API_KEY yok — EVDS serileri atlandı (önceki veri korunuyor)")
        sorun.append("evds")

    gerekli = {k for _, _, k in TUIK_TABLO}
    guncel = set()
    if a.tuik_yerel:
        T = {}
        import openpyxl
        for k in gerekli:
            f = os.path.join(a.tuik_yerel, k + ".xlsx")
            if os.path.exists(f):
                ws = openpyxl.load_workbook(f, data_only=True, read_only=True).worksheets[0]
                T[k] = ({"bulten": k, "donem": "yerel"}, [list(r) for r in ws.iter_rows(values_only=True)])
    else:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"})
        try:
            T = tuik_indir(s, gerekli, D.get("tuik"), guncel)
        except Exception as e:
            log(f"HATA TÜİK bülten listesi: {type(e).__name__}: {e}")
            T = {}
    tu = D.setdefault("tuik", {})
    for k in sorted(gerekli):
        if k not in T:
            if k not in guncel:
                sorun.append("tuik_" + k)
            continue
        bilgi, R = T[k]
        try:
            if k in BLOK:
                v = uretim_endeksi(R, BLOK[k])
            elif k in ("isgucu", "genc"):
                v = isgucu_tablo(R, ["nufus", "isgucu", "istihdam", "issiz", "disi", "katilim", "istihdam_orani", "issizlik"])
            elif k == "atil":
                v = isgucu_tablo(R, ["issizlik", "zaman_eksik", "potansiyel", "atil"])
            elif k == "ulke":
                v = ulke_tablo(R)
            tu[k] = {**v, "kaynak": bilgi}
            n = len(v.get("dates", v.get("ihr", [])))
            log(f"   {k}: {n} satır" + (f", {len(v['bloklar'])} blok ({', '.join(b['ad'][:18] for b in v['bloklar'])})" if "bloklar" in v else "")
                + (f", son {v['dates'][-1]}" if v.get("dates") else ""))
        except Exception as e:
            log(f"HATA TÜİK {k} ayrıştırılamadı: {type(e).__name__}: {e}")
            sorun.append("tuik_" + k)
    D["updated"] = simdi()
    D["failed"] = sorun
    json.dump(D, open(yol, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    log(f"yazıldı: {yol} ({os.path.getsize(yol) // 1024} KB)")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(KOK), "ortak"))
        from durum import yaz
        son = max((v["dates"][-1] for v in tu.values() if v.get("dates")), default=None)
        if son:
            yaz(a.site, "ekonomi", son)
    except Exception as e:
        log(f"durum.json yazılamadı: {e}")
    log(f"TAMAM — sorunlu: {', '.join(sorun) or 'yok'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
