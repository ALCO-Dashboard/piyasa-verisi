"""Finansal rapor PDF'inin dipnotlarından tablo okuma (BDDK şablonu):
  - Tüketici kredileri, bireysel kredi kartları, personel kredileri ve personel kredi kartlarına ilişkin bilgiler
  - Mevduatın / toplanan fonların (katılım fonlarının) vade yapısı
Cari dönem ve önceki dönem (önceki yıl sonu) tabloları okunur. Tutarlar milyon TL'ye çevrilir.
"""
import io
import re

SURUM = 2          # ayrıştırıcı sürümü: artınca eksik okunmuş raporlar yeniden denenir
SAYI = r"(?:-{1,2}|—|–|\(?\d{1,3}(?:[.,]\d{3})+(?:\.\d{2}(?!\d))?\)?|\(?\d+\)?)"
SATIR_SON = re.compile(rf"((?:\s+{SAYI})+)\s*$")


def pdf_ac(icerik):
    """KAP dosya indirme yanıtı PDF'i bir sarmalayıcı içinde döndürebilir: %PDF … %%EOF arası alınır."""
    i, j = icerik.find(b"%PDF"), icerik.rfind(b"%%EOF")
    return icerik[i:j + 5] if i >= 0 and j > i else icerik


def sayfalar(icerik):
    import logging
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    import pypdf
    r = pypdf.PdfReader(io.BytesIO(pdf_ac(icerik)))
    out = []
    for p in r.pages:
        try:
            out.append(p.extract_text() or "")
        except Exception:
            out.append("")
    return out


def birim(metin):
    """Sayfa başlığındaki para birimi → milyon TL çarpanı."""
    t = metin.lower()
    if re.search(r"milyar\s+(türk\s+)?lira", t):
        return 1000.0
    if re.search(r"milyon\s+(türk\s+)?lira|milyon\s+tl", t):
        return 1.0
    if re.search(r"bin\s+(türk\s+)?lira|bin\s+tl", t):
        return 0.001
    return None


def birim_genel(sayfa_metinleri):
    """Sayfa başlığında birim yoksa belgede en sık geçen ifade (ör. "aksi belirtilmediği müddetçe milyon Türk lirası")."""
    t = kucuk(re.sub(r"\s+", " ", " ".join(sayfa_metinleri)))
    m = len(re.findall(r"milyon (türk )?lira|milyon tl", t))
    b = len(re.findall(r"bin (türk )?lira|bin tl", t))
    return 1.0 if m and m >= b else 0.001 if b else None


def sayi(t):
    t = t.strip()
    if t in ("-", "--", "—", "–"):
        return 0.0
    neg = t.startswith("(") and t.endswith(")")
    t = re.sub(r"\.\d{2}$", "", t.strip("()")) if re.search(r",\d{3}\.\d{2}$", t.strip("()")) else t.strip("()")
    t = t.replace(".", "").replace(",", "")
    return -float(t) if neg else float(t)


def kucuk(s):
    return s.replace("İ", "i").replace("I", "ı").lower().replace("î", "i").replace("â", "a").replace("û", "u")


PARCA = re.compile(r"[\d.,()]+|-{1,2}|—|–")


def _toplam_tutar(v):
    """Satırın son sütunu (toplam) önceki sütunların toplamı mı?"""
    return abs(sum(v[:-1]) - v[-1]) <= max(2.0, abs(v[-1]) * 0.002)


def _onar(s, n):
    """PDF'te sayıların içine boşluk girmişse ("33 .084", "22, 629", "1 7.905") parçaları birleştirip
    satır toplamını tutan n sayılık okumayı ara. Bulunursa (etiket, değerler)."""
    t = s.split()
    k = len(t)
    while k and PARCA.fullmatch(t[k - 1]):
        k -= 1
    etiket, p = " ".join(t[:k]), t[k:][-20:]
    if len(p) < n:
        return None
    tam = re.compile(SAYI)
    sonuc = []

    def ara(j, grup):                       # sondan başa: p[:j] kaldı, grup = bulunan sayılar (sondan)
        if sonuc:
            return
        if len(grup) == n:
            v = [sayi(x) for x in reversed(grup)]
            if _toplam_tutar(v):
                sonuc.append((" ".join([etiket] + p[:j]).strip(), v))
            return
        for i in range(j - 1, max(-1, j - 4), -1):      # en çok 3 parça birleşir
            g = "".join(p[i:j])
            if i < j - 1 and any(re.fullmatch(r"-{1,2}|—|–", x) for x in p[i:j]):
                break
            if tam.fullmatch(g):
                ara(i, grup + [g])
    ara(len(p), [])
    return sonuc[0] if sonuc else None


def satirlar(metin, n, toplamli=False):
    """Metni etiket + n sayı biçimindeki satırlara ayır; sayısı olmayan satırlar (kaymış etiketler) sonrakine eklenir,
    eksik sayılı satırlar (boş kalemler, harf aralıklı yazılar) atlanır. Her satır: (etiket, değerler, kendi) — kendi,
    etiketin yalnız o satıra ait kısmıdır (üstteki sütun başlıkları karışmasın diye).
    toplamli: son sütun satır toplamıdır; tutmazsa bölünmüş sayılar birleştirilerek yeniden okunur."""
    out, bekleyen = [], []
    duz = []
    for ham in metin.split("\n"):                  # yalnız sayılardan oluşan satır önceki satırın devamıdır (taşan hücreler)
        s = ham.replace("\u00a0", " ").strip()
        if not s:
            continue
        if duz and re.fullmatch(rf"(?:{SAYI}\s*)+", s) and len(re.findall(SAYI, duz[-1])) < n and re.search(rf"{SAYI}\s*$", duz[-1]):
            duz[-1] += " " + s
        else:
            duz.append(s)
    for s in duz:
        m = SATIR_SON.search(" " + s)
        toks = re.findall(SAYI, m.group(1)) if m else []
        if m and 2 <= len(toks) < n:                 # boş hücreler çift boşluk olarak kalmış olabilir
            ara = re.findall(SAYI, re.sub(r"(?<=\S) {2,}(?=\S)", " - ", m.group(1).strip()))
            if len(ara) == n:
                toks = ara
        kendi = (" " + s)[:m.start(1)].strip() if m else ""
        vals = [sayi(x) for x in toks[-n:]] if len(toks) >= n else None
        if toplamli and len(toks) >= 2 and not (vals and _toplam_tutar(vals)):
            o = _onar(s, n)
            if o:
                kendi, vals = o
        if vals:
            etiket = " ".join(bekleyen[-3:] + [kendi]).strip()
            if etiket and not re.fullmatch(r"[\d\s().,-]*", etiket):
                out.append((re.sub(r"\s+", " ", etiket), vals, re.sub(r"\s+", " ", kendi or (bekleyen[-1] if bekleyen else ""))))
            bekleyen = []
        elif len(toks) >= 2 or re.search(r"-{3,}", s):
            bekleyen = []
        else:
            bekleyen.append(s)
    return out


def sikistir(t):
    """Boşlukları atılmış küçük harfli metin ve özgün metindeki konum eşlemesi (PDF'te kelime içine giren boşluklar için)."""
    q, ix = [], []
    for i, ch in enumerate(t):
        if not ch.isspace():
            q.append(kucuk(ch))
            ix.append(i)
    return "".join(q), ix


CARI = re.compile(r"cari\s*d\s*[öo]\s*n\s*e\s*m", re.I)
ONCEKI = re.compile(r"[öo]\s*n\s*c\s*e\s*k\s*i\s*d\s*[öo]\s*n\s*e\s*m", re.I)


def bloklar(sayfa_metinleri, baslik, sayfa_say=3):
    """Başlığı (boşluksuz, küçük harf metinde aranan desen) içeren her yer için aday: (cari, önceki, birim).
    'Cari dönem' etiketi yoksa tablo başlığın hemen altından başlar; 'Önceki dönem' varsa ikinci tablo odur."""
    for i, t in enumerate(sayfa_metinleri):
        q, ix = sikistir(t)
        for m in re.finditer(baslik, q):
            bas = ix[m.end() - 1] + 1 if m.end() - 1 < len(ix) else len(t)
            metin = t[bas:] + "\n" + "\n".join(sayfa_metinleri[i + 1:i + sayfa_say])
            ilk = re.search(rf"^.*?(?:\s{SAYI}){{3,}}\s*$", metin, re.M)          # ilk veri satırı
            c = CARI.search(metin, 0, ilk.start() if ilk else 2500)
            cs = c.start() if c else 0
            o = ONCEKI.search(metin, cs + 10)
            yield metin[cs:(o.start() if o else len(metin))], (metin[o.start():] if o else ""), \
                birim(t) or birim("\n".join(sayfa_metinleri[max(0, i - 2):i])) or birim_genel(sayfa_metinleri)


# ---------------------------------------------------------------- bireysel krediler
def _bireysel(metin):
    rows = satirlar(metin, 1)          # satırın son sayısı toplamdır (bazı bankalarda boş hücreler, ek tahakkuk sütunu)
    if not rows:
        return None
    out = {"konut": 0.0, "tasit": 0.0, "ihtiyac": 0.0, "diger": 0.0, "kk": 0.0, "kmh": 0.0, "tp": 0.0, "yp": 0.0, "toplam": None}
    ust = None
    for et, v, _ in rows:
        e = kucuk(et)
        tot = v[-1]
        if re.match(r"^toplam", e) or re.search(r"(^|\s)toplam\s*(\(.*\))?\s*$", e):
            out["toplam"] = tot
            break
        if re.search(r"(tüketici|personel)\s+kredi(leri)?\s*[-–]", e):
            ust = ("tk", "yp" if re.search(r"[-–]\s*yp", e) else "tp")
            out[ust[1]] += tot
            continue
        if re.search(r"kredi\s+kart", e):
            ust = ("kk", "yp" if re.search(r"[-–]\s*yp", e) else "tp")
            out["kk"] += tot
            out[ust[1]] += tot
            continue
        if re.search(r"kredili\s+mevduat", e):
            ust = None
            out["kmh"] += tot
            out["yp" if "yp" in e else "tp"] += tot
            continue
        if ust and ust[0] == "tk":
            k = "konut" if "konut" in e else "tasit" if "taşıt" in e or "tasit" in e else "ihtiyac" if "ihtiyaç" in e or "ihtiyac" in e else "diger"
            out[k] += tot
    if out["toplam"] is None:
        return None
    return out


def bireysel(sayfa_metinleri):
    ok = lambda d: d if d and d["toplam"] and abs(d["tp"] + d["yp"] - d["toplam"]) <= max(1, abs(d["toplam"]) * 0.01) else None
    for cari, onceki, c in bloklar(sayfa_metinleri, r"tüketicikredileri,?bireyselkredikart"):
        a, b = ok(_bireysel(cari)), ok(_bireysel(onceki or ""))
        if a and c:
            break
    else:
        return None
    olcek = lambda d: {k: round(v * c, 1) for k, v in d.items()} if d else None
    return {"cari": olcek(a), "onceki": olcek(b)}


# ---------------------------------------------------------------- mevduat / katılım fonu vade yapısı
# ortak vade kovaları: vadesiz, 1 aya kadar, 1-3 ay, 3-6 ay, 6-12 ay, 1 yıl ve üstü (birikimli dahil)
KOVA = ["vadesiz", "a1", "a3", "a6", "a12", "y1"]


def _mevduat(metin):
    """Mevduat bankası tablosu: Vadesiz, 7 gün ihbarlı (bazı bankalarda yok), 1 aya kadar, 1-3, 3-6, 6-12, 1 yıl+, birikimli, toplam."""
    yedi = bool(re.search(r"7\s*g[üu]n", metin[:400], re.I))
    rows = satirlar(metin, 9 if yedi else 8, toplamli=True)
    out = {}
    for et, v, kendi in rows:
        e = kucuk(et)
        ke = kucuk(kendi)
        if not yedi:
            v = [v[0], 0.0] + v[1:]
        kova = [v[0], v[1] + v[2], v[3], v[4], v[5], v[6] + v[7]]
        son = e[-60:]
        k = ("toplam" if ke.startswith("toplam") or re.search(r"(^|\s)toplam\s*(\(.*\))?$", ke) else
             "tasarruf" if "tasarruf" in e else "dth" if re.search(r"döviz\s+tevdiat", e) else "resmi" if e.startswith("resmi") or "resmi kur" in e
             else "ticari" if e.startswith("tic") else "diger" if e.startswith("diğ") or e.startswith("dig") else "km" if "kıymetli" in e or "kiymetli" in e
             else "bnk" if "bankalararası" in e or "bankalar arası" in e or e.startswith("bankalar mevduat") else None)
        if k and k not in out:
            out[k] = kova + [v[8]]
        if k == "toplam":
            break
    if "toplam" not in out:
        return None
    return {"gk_tl": out.get("tasarruf"), "tz_tl": _top(out.get("ticari"), out.get("diger")), "resmi": out.get("resmi"),
            "yp": out.get("dth"), "km": out.get("km"), "bnk": out.get("bnk"), "fon": None, "toplam": out["toplam"]}


def _top(*xs):
    xs = [x for x in xs if x]
    return [sum(t) for t in zip(*xs)] if xs else None


def _eksi(a, *bs):
    if not a:
        return None
    bs = [b for b in bs if b]
    return [x - sum(t) for x, t in zip(a, zip(*bs))] if bs else a


def _katilim(metin):
    """Katılım bankası tablosu: Vadesiz, 1 ay, 3 ay, 6 ay, 9 ay, 1 yıl, 1 yıl+, birikimli, toplam; satırlar I … XV."""
    rows = satirlar(metin, 9, toplamli=True)
    ana, alt, cur = {}, {}, None
    for et, v, kendi in rows:
        e = kucuk(et)
        ke = kucuk(kendi)
        kova = [v[0], v[1], v[2], v[3], v[4] + v[5], v[6] + v[7]] + [v[8]]
        rm = re.findall(r"(?:^|\s)(XV|XIV|XIII|XII|XI|IX|X|VIII|VII|VI|IV|V|III|II|I)\s*\.", et)
        if re.search(r"(^|\s)toplam\s*\(", ke) or re.match(r"^\s*toplam", ke):
            ana["toplam"] = kova
            break
        if rm:
            cur = rm[-1]
            ana.setdefault(cur, kova)
            continue
        if cur and ("resmi" in e):
            alt.setdefault((cur, "resmi"), kova)
        if cur and re.search(r"^bankalar", e):
            alt.setdefault((cur, "bnk"), kova)
    if "toplam" not in ana:
        return None
    g = lambda *ks: _top(*[ana.get(k) for k in ks])
    a = lambda k, t: alt.get((k, t))
    resmi = _top(a("III", "resmi"), a("IV", "resmi"))
    bnk = _top(a("III", "bnk"), a("IV", "bnk"), a("VII", "bnk"), a("VIII", "bnk"))
    return {"gk_tl": g("I", "II"), "tz_tl": _eksi(g("III", "IV"), resmi, a("III", "bnk"), a("IV", "bnk")), "resmi": resmi,
            "yp": _eksi(g("V", "VI", "VII", "VIII", "XI", "XIV"), a("VII", "bnk"), a("VIII", "bnk")), "km": g("IX", "XII", "XV"), "bnk": bnk,
            "fon": g("X", "XIII"), "toplam": ana["toplam"]}


def vade(sayfa_metinleri, katilim):
    if katilim:
        desen, f = r"(toplananfonların|katılımfonu(nun|larının)|fonlarının)vadeyapısı", _katilim
    else:
        desen, f = r"(mevduatın|toplananfonların)[^.:]{0,40}vadeyapısı", _mevduat
    for cari, onceki, c in bloklar(sayfa_metinleri, desen):
        a, b = tutarli(f(cari)), tutarli(f(onceki or ""))
        if a and c:
            break
    else:
        return None
    olcek = lambda d: {k: ([round(x * c, 1) for x in v] if v else None) for k, v in d.items()} if d else None
    return {"cari": olcek(a), "onceki": olcek(b)}


def tutarli(d):
    """Kategoriler toplamı tablo toplamını (%1) tutmuyorsa okuma güvenilmez: None."""
    if not d or not d.get("toplam"):
        return None
    t = d["toplam"][-1]
    s = sum(v[-1] for k, v in d.items() if k != "toplam" and v)
    return d if t and abs(s - t) <= abs(t) * 0.01 else None


def oku(icerik, katilim, ad=None):
    S = sayfalar(icerik)
    import os
    if os.environ.get("DIPNOT_DEBUG") and ad:      # test: sayfa metinlerini kaydet
        open(os.path.join(os.environ["DIPNOT_DEBUG"], ad + ".txt"), "w", encoding="utf-8").write("\n\f\n".join(S))
    return {"bireysel": bireysel(S), "vade": vade(S, katilim)}
