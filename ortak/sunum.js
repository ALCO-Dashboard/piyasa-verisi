// Sunum oluşturucu — sitenin her sayfasında çalışır (ortak/ust.js yükler).
//  • Seçim modu: kart, grafik ve tabloların üzerine gelince "＋ Sunuma ekle" çıkar; seçilenler sunum taslağına eklenir.
//    Taslak tarayıcıda (localStorage "alco-sunum") durur; sekmeler, iç sayfalar ve Sunum sayfası aynı taslağı görür.
//  • İzole gösterim (?sunum=1): Sunum sayfası her slayttaki alanı kaynak sayfayı iframe içinde açarak gösterir;
//    sayfa kaydedilen duruma (alt sekme, seçili düğmeler) getirilir, alan dışındaki her şey gizlenir. Böylece slayt
//    her açılışta güncel veriyle, sitenin kendi grafiğiyle gelir.
(function () {
  if (window.alcoSunum) return;
  const me = document.currentScript || {};
  const DS = me.dataset || {};
  const ROOT = DS.root || "./", PAGE = DS.page || "";
  const KOK = new URL(ROOT, location.href);
  const SAYFA = (() => { let p = decodeURIComponent(location.pathname); const r = decodeURIComponent(KOK.pathname); if (p.startsWith(r)) p = p.slice(r.length); return p.replace(/index\.html$/, ""); })();
  const Q = new URLSearchParams(location.search);
  const IZOLE = Q.has("sunum");
  const UST = window.top === window;
  const K = "alco-sunum", KM = "alco-sunum-mod";
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const bekle = ms => new Promise(r => setTimeout(r, ms));
  const uid = () => Math.random().toString(36).slice(2, 9) + Date.now().toString(36).slice(-3);
  const ls = { get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} } };

  // ---- sayfa ve alt sekme adları (slayt kaynak etiketi ve otomatik başlıklar için)
  const SAYFA_AD = { "ozet/": "Özet", "bankacilik/": "Bankacılık Verileri", "tefas.html": "TEFAS Verileri", "makro/": "Makro ve Piyasa", "bilanco/": "Banka Bilanço Verileri", "tcmb/": "TCMB Rezervler", "zk/": "Zorunlu Karşılık", "katilim/": "Katılım Bülteni" };
  const SEKME_GRUP = /^(tabs|tSub|mkTabs|psTabs|sTabs|gTabs|sekme|menu|bFreq)$/;

  // ---- metin yardımcıları
  const AYLAR = "ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık|oca|şub|mar|nis|may|haz|tem|ağu|eyl|eki|kas|ara";
  const norm = s => String(s || "").toLocaleLowerCase("tr").replace(/\d+/g, " ").replace(new RegExp(`\\b(${AYLAR})\\b`, "g"), " ")
    .replace(/[^a-zçğıöşü]+/g, " ").replace(/\s+/g, " ").trim();
  const metin = el => (el?.textContent || "").replace(/\s+/g, " ").trim();
  const gorunur = x => x && !x.closest("[hidden]") && x.getClientRects().length > 0;
  function baslik(el) {
    const ilk = sel => [...el.querySelectorAll(sel)].find(h => metin(h) && gorunur(h));
    let t = el.matches("h1,h2,h3,h4") ? metin(el) : metin(ilk("h1,h2,h3,h4,.cardhead h3,.t span,.ttl,.title,.hd,caption,legend"));
    if (!t) t = el.getAttribute("aria-label") || el.getAttribute("title") || "";
    if (!t) t = metin(ilk("b,strong,th,.k,.lbl,.nm,.pl,.lab,.label"));
    if (!t) { const y = [...el.querySelectorAll("*")].find(x => !x.children.length && metin(x) && gorunur(x)); t = metin(y) || metin(el).slice(0, 50); }
    return t.replace(/\s*(Detay →|↗)\s*$/, "").slice(0, 90);
  }

  // ---- tarayıcı veritabanı: kayıt klasörü ve ekran görüntüleri (taslak localStorage'a sığmayacak kadar büyük olabilir)
  const idb = (() => {
    let p;
    const ac = () => p || (p = new Promise((ok, no) => {
      const r = indexedDB.open("alco-sunum", 2);
      r.onupgradeneeded = () => { const d = r.result; ["ayar", "resim"].forEach(n => { if (!d.objectStoreNames.contains(n)) d.createObjectStore(n); }); };
      r.onsuccess = () => { r.result.onversionchange = () => { r.result.close(); p = null; }; ok(r.result); };
      r.onerror = () => { p = null; no(r.error); };
    }));
    const is = (st, mod, f) => ac().then(d => new Promise((ok, no) => { const q = f(d.transaction(st, mod).objectStore(st)); q.onsuccess = () => ok(q.result); q.onerror = () => no(q.error); }));
    return { get: (st, k) => is(st, "readonly", x => x.get(k)), set: (st, k, v) => is(st, "readwrite", x => x.put(v, k)), sil: (st, k) => is(st, "readwrite", x => x.delete(k)) };
  })();

  // ---- sunum taslağı (localStorage)
  const yeniSunum = () => ({ v: 1, ad: "", tema: "light", kapak: { goster: true, baslik: "Haftalık Piyasa Değerlendirmesi", alt: "Aktif Pasif Yönetimi" },
    gundem: { goster: true }, kapanis: { goster: true, baslik: "Teşekkürler", alt: "" }, slaytlar: [] });
  const oku = () => { try { const d = JSON.parse(ls.get(K)); if (d && Array.isArray(d.slaytlar)) return d; } catch (e) {} return yeniSunum(); };
  const dinleyici = new Set();
  const yaz = d => { d.degisti = Date.now(); ls.set(K, JSON.stringify(d)); dinleyici.forEach(f => { try { f(d); } catch (e) {} }); };
  addEventListener("storage", e => { if (e.key === K) dinleyici.forEach(f => { try { f(oku()); } catch (x) {} }); if (e.key === KM) modDegisti(); });
  const ogeler = d => d.slaytlar.flatMap(s => s.ogeler);

  // Her ekleme yeni slayt açar; Ctrl (Mac'te Cmd) basılıyken eklenen alan, bir önceki eklemenin yapıldığı slayta girer
  // (birbiriyle bağlantılı kutucuk ve grafikleri aynı slaytta toplamak için).
  const kucukMu = o => o.w * o.h < 70000 || (o.w < 330 && o.h < 260);
  const sonHedef = d => d.slaytlar.find(s => s.id === d.sonSlayt) || d.slaytlar[d.slaytlar.length - 1] || null;
  function ekle(o, ayni) {
    const d = oku(); o.kucuk = kucukMu(o);
    const h = ayni ? sonHedef(d) : null;
    if (h) { h.ogeler.push(o); h.kilit = true; d.sonSlayt = h.id; }
    else { const s = { id: uid(), baslik: o.kucuk ? (o.yolAd.split(" › ").pop() || o.ad) : o.ad, not: "", oc: null, kaynak: null, duzen: "oto", ogeler: [o] }; d.slaytlar.push(s); d.sonSlayt = s.id; }
    yaz(d); return d;
  }
  const slaytNo = (d, id) => d.slaytlar.findIndex(s => s.id === id) + 1;
  function cikar(id) {
    const d = oku();
    d.slaytlar.forEach(s => { s.ogeler = s.ogeler.filter(x => x.id !== id); });
    d.slaytlar = d.slaytlar.filter(s => s.ogeler.length || s.tur);
    yaz(d); return d;
  }

  // ---- sayfa durumu: alt sekmeler, seçili düğmeler, açılır listeler, adres (#)
  const DUGME = "button[aria-pressed],button[aria-selected],[role=tab][aria-selected],a[aria-selected]";
  const durumu = b => (b.getAttribute("aria-pressed") ?? b.getAttribute("aria-selected")) === "true";
  function anahtar(b) {
    const ds = Object.entries(b.dataset || {}).filter(([k]) => !/^ss/.test(k)).sort();
    return ds.length ? "d:" + ds.map(([k, v]) => k + "=" + v).join("&") : "t:" + norm(metin(b));
  }
  const grupOf = b => b.parentElement && b.parentElement.closest("[id]");
  // onay kutuları ve seçenekler (ör. TCMB › Faiz, Kâr Payı: soldaki konu listesi; BDDK tablolarında grafiğe eklenen satırlar)
  const KUTU = "input[type=checkbox],input[type=radio]", TARIH = "input[type=date],input[type=month]";
  const dsMetin = e => Object.entries(e.dataset || {}).filter(([k]) => !/^ss/.test(k)).sort().map(([k, v]) => k + "=" + v).join("&");
  function girdiAnah(x) {
    const d = dsMetin(x); if (d) return "d:" + d;
    const r = x.parentElement && x.parentElement.closest("[data-s],[data-n],[data-m],[data-t],[data-g],[data-k],[data-id]"), g = grupOf(x);
    if (r && (!g || g.contains(r))) { const rd = dsMetin(r); if (rd) return "r:" + rd; }
    const l = x.closest("label"); if (l && metin(l)) return "l:" + norm(metin(l));
    return "n:" + (x.name || "") + "=" + (x.type === "radio" ? x.value : "");
  }
  function girdiler(sec) {       // [{g, k, el}] — aynı anahtar tekrar ederse sıra numarası eklenir
    const say = {}, out = [];
    $$(sec).forEach(x => { if (x.closest("#alcoTop,.ss-ui")) return; const g = grupOf(x); if (!g || g === document.body) return;
      let k = girdiAnah(x); const a = g.id + "|" + k; say[a] = (say[a] || 0) + 1; if (say[a] > 1) k += "#" + say[a]; out.push({ g: g.id, k, el: x }); });
    return out;
  }
  function durumAl() {
    const b = [];
    $$(DUGME).forEach(x => { if (x.closest("#alcoTop,.ss-ui")) return; const g = grupOf(x); if (!g || g === document.body) return;
      b.push({ g: g.id, k: anahtar(x), v: durumu(x), sek: x.getAttribute("role") === "tab" || x.hasAttribute("aria-selected") || SEKME_GRUP.test(g.id) }); });
    const s = $$("select[id]").filter(x => !x.closest(".ss-ui")).map(x => ({ s: x.id, v: x.value }));
    const c = girdiler(KUTU).map(x => ({ g: x.g, k: x.k, v: x.el.checked }));
    const t = girdiler(TARIH).filter(x => x.el.value).map(x => ({ g: x.g, k: x.k, v: x.el.value }));
    return { b, s, c, t, h: location.hash };
  }
  // durum imzası: alt sekmeler + alanın kendi içindeki düğme, kutu ve listeler (ör. BDDK kartında TL kredi / TL mevduat)
  const imza = (st, ic) => (st.b || []).filter(x => x.v && (x.sek || !ic || ic.includes(x.g))).map(x => x.g + ":" + x.k).sort().join("|") + "#" + (st.s || []).filter(x => !ic || ic.includes(x.s)).map(x => x.s + "=" + x.v).sort().join("|")
    + "#" + (st.c || []).filter(x => x.v && (!ic || ic.includes(x.g))).map(x => x.g + ":" + x.k).sort().join("|");
  function yolAd() {     // "Bankacılık Verileri › TCMB › Para Politikası"
    let ust = null; try { if (!UST && parent.alcoSunum && !parent.document.getElementById("alcoFrames")) ust = parent.alcoSunum._yolAd(); } catch (e) {}
    const p = ust ? ust.split(" › ") : [SAYFA_AD[SAYFA] || document.title.replace(/\s*·.*$/, "")];
    $$(DUGME).forEach(x => { const g = grupOf(x); if (g && SEKME_GRUP.test(g.id) && durumu(x) && x.offsetParent) { const t = metin(x).replace(/\s*\d+.*$/, "").trim(); if (t && !p.includes(t)) p.push(t); } });
    return p.join(" › ");
  }
  async function durumUygula(st) {
    if (!st) return 0;
    let top = 0;
    if (st.h && location.hash !== st.h) { try { location.hash = st.h; } catch (e) {} await bekle(250); top++; }
    for (let tur = 0; tur < 6; tur++) {
      let deg = 0;
      const sira = [...(st.b || [])].sort((a, b) => (b.sek - a.sek) || (b.v - a.v));
      for (const x of sira) {
        const g = document.getElementById(x.g); if (!g) continue;
        const btn = $$(DUGME, g).find(b => grupOf(b) === g && anahtar(b) === x.k) || $$(DUGME, g).find(b => anahtar(b) === x.k);
        if (!btn || durumu(btn) === x.v) continue;
        if (!x.v) {
          if (!btn.hasAttribute("aria-pressed")) continue;                  // sekme "seçili değil" yapılamaz
          const grp = (st.b || []).filter(y => y.g === x.g), acik = grp.filter(y => y.v).length;
          if (acik === 1 && grp.length > 1) continue;                       // tek seçimli grup: doğru düğme seçilince bu kendiliğinden kapanır
        }
        try { btn.click(); } catch (e) {} deg++; await bekle(70);
      }
      for (const s of st.s || []) {
        const e = document.getElementById(s.s);
        if (e && e.value !== s.v && [...(e.options || [])].some(o => o.value === s.v)) { e.value = s.v; e.dispatchEvent(new Event("input", { bubbles: true })); e.dispatchEvent(new Event("change", { bubbles: true })); deg++; await bekle(70); }
      }
      if (st.c && st.c.length) {            // onay kutuları: sayfa her tıklamada yeniden çizilebilir; her seferinde taze bulunur
        for (const x of st.c) {
          const e = girdiler(KUTU).find(y => y.g === x.g && y.k === x.k); if (!e || e.el.checked === x.v || (e.el.type === "radio" && !x.v)) continue;
          try { e.el.click(); } catch (er) {} deg++; await bekle(90);
        }
      }
      for (const x of st.t || []) {
        const e = girdiler(TARIH).find(y => y.g === x.g && y.k === x.k); if (!e || e.el.value === x.v) continue;
        e.el.value = x.v; e.el.dispatchEvent(new Event("input", { bubbles: true })); e.el.dispatchEvent(new Event("change", { bubbles: true })); deg++; await bekle(90);
      }
      top += deg; if (!deg) break; await bekle(220);
    }
    return top;
  }

  // ---- alan (blok) bulma
  const BLOK = ".card,.kc,.tkp,.yan,.box,.panel,aside,article,.chartbox,.kpi,.tile,figure,table,.tw";
  const UIDISI = "#alcoTop,.ss-ui,html,body,main,header,nav.at-tabs,.wrap,#app,iframe";
  function blokMu(el) {
    if (!el || el.nodeType !== 1 || el.matches(UIDISI)) return false;
    const r = el.getBoundingClientRect(); if (r.width < 120 || r.height < 50) return false;
    if (r.width > innerWidth * .99 && r.height > innerHeight * 2.2) return false;      // tüm sayfayı kaplayan sarmalayıcılar
    if (el.matches(BLOK)) return true;
    const cs = getComputedStyle(el);
    const kenar = parseFloat(cs.borderTopWidth) > 0 && cs.borderTopStyle !== "none";
    return parseFloat(cs.borderTopLeftRadius) >= 6 && (kenar || cs.boxShadow !== "none") && r.width >= 180 && r.height >= 80;
  }
  function bloklar(el) { const a = []; for (let x = el; x && x !== document.body; x = x.parentElement) if (blokMu(x)) a.push(x); return a; }
  function cssYol(el) {
    const p = [];
    for (let x = el; x && x !== document.body; x = x.parentElement) {
      if (x.id) { p.unshift("#" + CSS.escape(x.id)); break; }
      let i = 1; for (let y = x.previousElementSibling; y; y = y.previousElementSibling) if (y.tagName === x.tagName) i++;
      p.unshift(x.tagName.toLowerCase() + ":nth-of-type(" + i + ")");
    }
    return p.join(" > ");
  }
  const sinif = el => [...el.classList].find(c => !/^ss-|^hidden$|^on$|^active$|^sel/.test(c)) || "";
  const dsAl = el => { for (const [k, v] of Object.entries(el.dataset || {})) if (!/^ss/.test(k) && v && v.length < 40) return [k, v]; return null; };
  function konum(el) {
    const tag = el.tagName.toLowerCase(), cls = sinif(el), n = norm(baslik(el));
    const ayni = $$(tag + (cls ? "." + CSS.escape(cls) : "")).filter(x => norm(baslik(x)) === n);
    return { id: el.id || "", tag, cls, n, i: Math.max(0, ayni.indexOf(el)), yol: cssYol(el), ds: dsAl(el) };
  }
  function bul(L) {
    if (!L) return null;
    if (L.id) { const e = document.getElementById(L.id); if (e) return e; }
    if (L.ds) { try { const e = document.querySelector(`${L.tag}${L.cls ? "." + CSS.escape(L.cls) : ""}[data-${L.ds[0].replace(/[A-Z]/g, m => "-" + m.toLowerCase())}="${CSS.escape(L.ds[1])}"]`); if (e) return e; } catch (e) {} }
    const ayni = $$(L.tag + (L.cls ? "." + CSS.escape(L.cls) : "")).filter(x => norm(baslik(x)) === L.n && !x.closest(".ss-ui"));
    if (ayni.length) return ayni[Math.min(L.i, ayni.length - 1)];
    try { const e = document.querySelector(L.yol); if (e && e.tagName.toLowerCase() === L.tag && (!L.cls || e.classList.contains(L.cls))) return e; } catch (e) {}
    return null;
  }
  function ogeYap(el) {
    const r = el.getBoundingClientRect();
    const ic = [...new Set([...$$(DUGME, el).map(b => grupOf(b)?.id), ...$$("select[id]", el).map(x => x.id), ...$$(KUTU, el).map(x => grupOf(x)?.id)].filter(Boolean))];
    const kk = /^Kaynak:/.test(el.getAttribute("title") || "") ? el.getAttribute("title").replace(/^Kaynak:\s*/, "") : "";
    return { id: uid(), sayfa: SAYFA, ad: baslik(el) || "Alan", yolAd: yolAd(), konum: konum(el), durum: durumAl(), ic, kk,
      w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), vw: innerWidth, t: Date.now() };
  }
  const buDurumda = (o, st) => imza(o.durum, o.ic) === imza(st || durumAl(), o.ic);
  function ekliMi(el, st) {
    const L = konum(el);
    return ogeler(oku()).find(o => o.sayfa === SAYFA && o.konum && o.konum.tag === L.tag && o.konum.cls === L.cls && o.konum.n === L.n && o.konum.i === L.i && buDurumda(o, st));
  }

  // ---- bağlı alanlar: bir grafik ve onu yöneten tıklanır kutucuklar (ör. TCMB › Para Politikası kutuları ve kırılım grafiği)
  const tiklanir = e => e.matches("button,[role=button],[role=tab],[aria-pressed],a[href]") || getComputedStyle(e).cursor === "pointer";
  const grafikMi = e => { if (!e.querySelector("svg,canvas")) return false; const r = e.getBoundingClientRect(); return r.height > 160 && r.width > 300; };
  function ustBloklar(kap) {
    if (!kap || kap === document.body || kap.querySelectorAll("*").length > 4000) return [];
    const a = $$("*", kap).filter(x => !x.closest(".ss-ui") && blokMu(x));
    return a.filter(e => !a.some(x => x !== e && x.contains(e)));
  }
  const domSira = (a, b) => a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
  let bagOnbellek = { el: null, grp: null };
  function baglilar(B) {
    if (bagOnbellek.el === B) return bagOnbellek.grp;
    let grp = null;
    try {
      if (tiklanir(B)) {               // kutucuk: kardeş kutucuklar + hemen önündeki/arkasındaki grafik
        let kap = B.parentElement, kutular = [];
        for (let i = 0; i < 3 && kap && kap !== document.body; i++, kap = kap.parentElement) { kutular = ustBloklar(kap).filter(tiklanir); if (kutular.length >= 2) break; }
        if (kutular.length >= 2) {
          let ch = null;
          for (let x = kap, i = 0; x && x !== document.body && i < 3 && !ch; x = x.parentElement, i++)
            for (const sb of [x.nextElementSibling, x.previousElementSibling]) { if (!sb) continue; const c = (blokMu(sb) ? [sb] : ustBloklar(sb)).find(e => grafikMi(e) && !tiklanir(e)); if (c) { ch = c; break; } }
          grp = [...kutular, ...(ch ? [ch] : [])];
        }
      } else if (grafikMi(B)) {        // grafik: hemen önündeki/arkasındaki kutucuk grubu
        for (let x = B, i = 0; x && x !== document.body && i < 4 && !grp; x = x.parentElement, i++)
          for (const sb of [x.previousElementSibling, x.nextElementSibling]) { if (!sb) continue; const k = ustBloklar(sb).filter(tiklanir); if (k.length >= 2) { grp = [...k, B]; break; } }
      }
    } catch (e) { grp = null; }
    if (grp) grp = [...new Set(grp)].sort(domSira);
    if (grp && (grp.length < 2 || grp.length > 16 || !grp.includes(B))) grp = null;
    bagOnbellek = { el: B, grp }; return grp;
  }

  // ---- seçim modu
  const modAcik = () => ls.get(KM) === "1";
  const CSS_UI = `
.ss-ui{font-family:"DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
.ss-hl{position:fixed;pointer-events:none;z-index:2147483000;border:2px solid #c8102e;border-radius:12px;background:rgba(200,16,46,.05);box-shadow:0 0 0 4px rgba(200,16,46,.12);transition:all .08s ease-out;display:none}
.ss-hl.ekli{border-style:solid;background:rgba(11,122,11,.05);border-color:#0b7a0b;box-shadow:0 0 0 4px rgba(11,122,11,.12)}
.ss-et{position:fixed;z-index:2147483001;display:none;flex-direction:column;align-items:stretch;gap:0;background:#c8102e;color:#fff;border-radius:9px;box-shadow:0 6px 18px rgba(0,0,0,.22);font-size:12.5px;font-weight:700;overflow:hidden;white-space:nowrap}
.ss-et .sat{display:flex;align-items:stretch}
.ss-et .sat.alt{background:#1c1416}
.ss-et .sat.alt button{font-weight:600}
.ss-et .sat+.sat{border-top:1px solid rgba(255,255,255,.22)}
.ss-kirp{position:fixed;inset:0;z-index:2147483004;cursor:crosshair;background:rgba(20,16,17,.18)}
.ss-kirp .ip{position:fixed;left:50%;top:14px;transform:translateX(-50%);background:#1c1416;color:#fff;border-radius:10px;padding:9px 14px;font:600 13px "DM Sans",system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.3);pointer-events:none}
.ss-kirp .kutu{position:fixed;border:2px solid #fff;box-shadow:0 0 0 2px #1d4ed8,0 0 0 9999px rgba(20,16,17,.35);border-radius:4px;display:none}
.ss-et.ekli{background:#0b7a0b}
.ss-hl.grup{border-color:#1d4ed8;background:rgba(29,78,216,.06);box-shadow:0 0 0 4px rgba(29,78,216,.14)}
.ss-et.grup{background:#1d4ed8}
.ss-et button{all:unset;cursor:pointer;padding:6px 10px;display:inline-flex;align-items:center;gap:5px;font:inherit}
.ss-et button:hover{background:rgba(255,255,255,.16)}
.ss-et button+button{border-left:1px solid rgba(255,255,255,.28)}
.ss-et .ad{font-weight:500;opacity:.85;max-width:220px;overflow:hidden;text-overflow:ellipsis}
.ss-rozet{position:absolute;z-index:2147482999;pointer-events:none;background:#0b7a0b;color:#fff;font:700 11px/1 "DM Sans",system-ui,sans-serif;border-radius:0 10px 0 8px;padding:5px 8px}
.ss-cerceve{position:absolute;z-index:2147482998;pointer-events:none;border:2px dashed #0b7a0b;border-radius:12px}
.ss-bag{position:fixed;z-index:2147482999;pointer-events:none;border:2px solid #1d4ed8;border-radius:12px;background:rgba(29,78,216,.07);box-shadow:0 0 0 3px rgba(29,78,216,.15)}
.ss-et button.bag{background:#1d4ed8}.ss-et button.bag:hover{background:#1e40af}
.ss-bar{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:2147483002;display:flex;align-items:center;gap:12px;flex-wrap:wrap;justify-content:center;
  background:#1c1416;color:#fff;border-radius:14px;padding:10px 12px 10px 16px;box-shadow:0 14px 40px rgba(0,0,0,.35);font-size:13.5px;max-width:calc(100vw - 24px)}
.ss-bar .nokta{width:9px;height:9px;border-radius:50%;background:#f0525f;box-shadow:0 0 0 4px rgba(240,82,95,.25);animation:ssn 1.6s infinite}
@keyframes ssn{50%{box-shadow:0 0 0 7px rgba(240,82,95,.05)}}
.ss-bar .ip{color:#cbbfc1;max-width:400px;line-height:1.35;font-size:12.5px}
.ss-bar .say{font-family:"DM Mono",ui-monospace,monospace;background:rgba(255,255,255,.1);border-radius:8px;padding:5px 9px;white-space:nowrap}
.ss-bar button{font:inherit;font-weight:700;border:0;border-radius:9px;padding:8px 13px;cursor:pointer;color:#fff;background:rgba(255,255,255,.12)}
.ss-bar button:hover{background:rgba(255,255,255,.2)}
.ss-bar button.ana{background:#c8102e}.ss-bar button.ana:hover{background:#a50d26}
.ss-bar button:disabled{opacity:.45;cursor:default}
.ss-pop{position:absolute;z-index:2147483003;min-width:300px;background:var(--at-bg,var(--surface,#fff));color:var(--at-ink,var(--ink,#1c1416));border:1px solid var(--at-line,var(--line,#eadfe0));border-radius:12px;box-shadow:0 16px 40px rgba(0,0,0,.18);padding:6px}
.ss-pop button{all:unset;box-sizing:border-box;display:grid;grid-template-columns:28px 1fr;gap:2px 8px;width:100%;padding:9px 10px;border-radius:9px;cursor:pointer;font:600 13.5px/1.3 "DM Sans",system-ui,sans-serif}
.ss-pop button:hover{background:var(--at-wash,#fdecee)}
.ss-pop button i{grid-row:span 2;font-style:normal;font-size:17px;line-height:1.2;text-align:center;color:var(--at-red,#c8102e)}
.ss-pop button small{font-weight:400;font-size:12px;color:var(--at-mut,#7a6a6c)}
.ss-pop hr{border:0;border-top:1px solid var(--at-line,#eadfe0);margin:4px 6px}
.ss-toast{position:fixed;left:50%;bottom:86px;transform:translateX(-50%);z-index:2147483003;background:#0b7a0b;color:#fff;border-radius:10px;padding:8px 14px;font:600 13px "DM Sans",system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.25);opacity:0;transition:opacity .2s;pointer-events:none}
.ss-toast.on{opacity:1}
html.ss-mod .kc .t span:last-child{opacity:0!important}
@media print{.ss-ui,.ss-hl,.ss-et,.ss-rozet,.ss-cerceve,.ss-bar{display:none!important}}`;
  function stilEkle() { if (document.getElementById("ssCss")) return; const s = document.createElement("style"); s.id = "ssCss"; s.textContent = CSS_UI; document.head.appendChild(s); }

  let hl, et, aday = [], seviye = 0, kilit = false, isaretler = [], ctrl = false;
  const ctrlAyarla = v => { v = !!v; if (v === ctrl) return; ctrl = v; if (hl && aday[0] && !kilit) ciz(); else if (et && kilit) ciz(); };
  function uiKur() {
    if (hl) return; stilEkle();
    hl = Object.assign(document.createElement("div"), { className: "ss-hl ss-ui" });
    et = Object.assign(document.createElement("div"), { className: "ss-et ss-ui" });
    document.body.append(hl, et);
    et.addEventListener("mouseenter", () => { kilit = true; });
    et.addEventListener("mouseleave", () => { kilit = false; bagGoster(null); });
    et.addEventListener("mouseover", e => { const b = e.target.closest("button"); bagGoster(b && b.dataset.a === "grup" ? baglilar(aday[seviye]) : null); });
    et.addEventListener("click", e => {
      e.preventDefault(); e.stopPropagation();
      const b = e.target.closest("button"); if (!b) return; const el = aday[seviye]; if (!el) return;
      if (b.dataset.a === "buyut") { seviye = Math.min(aday.length - 1, seviye + 1); ciz(); return; }
      if (b.dataset.a === "kucult") { seviye = Math.max(0, seviye - 1); ciz(); return; }
      if (b.dataset.a === "foto") { fotoAlan(el, e.ctrlKey || e.metaKey); return; }
      if (b.dataset.a === "kirp") { kirp(e.ctrlKey || e.metaKey); return; }
      if (b.dataset.a === "grup") {
        const grp = baglilar(el); if (!grp) return;
        bagGoster(null);
        let d = null; grp.forEach((g, i) => { d = ekle(ogeYap(g), i > 0 || e.ctrlKey || e.metaKey); });
        const sl = d.slaytlar.find(x => x.id === d.sonSlayt), gr = grp.find(g => grafikMi(g) && !tiklanir(g));
        if (sl && gr && sl.ogeler.length === grp.length) { sl.baslik = baslik(gr); yaz(d); }
        toast(`Bağlı ${grp.length} alan eklendi · Slayt ${slaytNo(d, d.sonSlayt)}`); ciz(); isaretle(); return;
      }
      const var_ = ekliMi(el), ayni = e.ctrlKey || e.metaKey;
      if (var_) { cikar(var_.id); toast("Sunumdan çıkarıldı"); }
      else { const d = ekle(ogeYap(el), ayni), n = slaytNo(d, d.sonSlayt); toast(ayni && d.slaytlar[n - 1].ogeler.length > 1 ? `Aynı slayta eklendi · Slayt ${n}: ${d.slaytlar[n - 1].ogeler.length} alan` : `Eklendi · Slayt ${n}`); }
      ciz(); isaretle();
    });
  }
  function ciz() {
    const el = aday[seviye]; if (!el || !el.isConnected) { hl.style.display = et.style.display = "none"; return; }
    const r = el.getBoundingClientRect(), ek = !!ekliMi(el), d = oku(), h = sonHedef(d), grup = ctrl && !ek && h;
    Object.assign(hl.style, { display: "block", left: r.left - 3 + "px", top: r.top - 3 + "px", width: r.width + 6 + "px", height: r.height + 6 + "px" });
    hl.classList.toggle("ekli", ek); et.classList.toggle("ekli", ek); hl.classList.toggle("grup", !!grup); et.classList.toggle("grup", !!grup);
    const kisa = t => { t = String(t || ""); return t.length > 28 ? t.slice(0, 27) + "…" : t; };
    const etiket = ek ? "✓ Sunumda · çıkar" : grup ? `＋ Aynı slayta ekle (Slayt ${slaytNo(d, h.id)}: ${esc(kisa(h.baslik))})` : "＋ Sunuma ekle";
    et.title = ek ? "" : grup ? `Ctrl basılı: önceki eklemenin slaytına (${h.baslik}) eklenir` : "Yeni slayt olarak eklenir · Ctrl'e basılı tutarak tıklarsanız önceki slayta eklenir";
    const grp = !ek ? baglilar(el) : null;
    et.innerHTML = `<div class="sat"><button data-a="ekle">${etiket} <span class="ad">${esc(baslik(el))}</span></button>` +
      (grp ? `<button data-a="grup" class="bag" title="Grafik ve onu yöneten ${grp.length - 1} kutucuk aynı slayta, sitedeki yerleşimleriyle eklenir; slaytta kutucuğa tıklayınca grafik değişir">⧉ Bağlı alanlarla (${grp.length})</button>` : "") +
      (seviye < aday.length - 1 ? `<button data-a="buyut" title="Daha geniş alanı seç">⤢</button>` : "") + (seviye > 0 ? `<button data-a="kucult" title="Daha dar alanı seç">⤡</button>` : "") + `</div>` +
      `<div class="sat alt"><button data-a="foto" title="Bu alanın şu anki görüntüsü sabit resim olarak eklenir (veriler güncellenmez)">📷 Ekran görüntüsü olarak ekle</button><button data-a="kirp" title="Sayfada istediğiniz bölgeyi fareyle çizerek görüntüsünü alın">✂ Bölge çiz</button></div>`;
    et.style.display = "flex";
    const ew = et.offsetWidth, eh = et.offsetHeight;
    let x = Math.min(innerWidth - ew - 6, Math.max(6, r.right - ew - 8)), y = r.top + 8;
    if (y < 4) y = 4; if (y > innerHeight - eh - 4) y = Math.max(4, Math.min(innerHeight - eh - 4, r.bottom - eh - 8));
    et.style.left = x + "px"; et.style.top = y + "px";
  }
  let bagCer = [];
  function bagGoster(grp) {
    bagCer.forEach(x => x.remove()); bagCer = [];
    if (!grp) return; stilEkle();
    grp.forEach(g => { const r = g.getBoundingClientRect(), c = Object.assign(document.createElement("div"), { className: "ss-bag ss-ui" });
      Object.assign(c.style, { left: r.left - 3 + "px", top: r.top - 3 + "px", width: r.width + 6 + "px", height: r.height + 6 + "px" }); document.body.appendChild(c); bagCer.push(c); });
  }
  function hareket(e) {
    if (!modAcik() || PAGE === "sunum" || kirpAcik) return;
    ctrlAyarla(e.ctrlKey || e.metaKey);
    if (kilit) return;
    if (e.target.closest && e.target.closest(".ss-ui")) return;
    const a = bloklar(e.target);
    if (a[0] !== aday[0]) { aday = a; seviye = 0; }
    ciz();
  }
  function isaretle() {
    isaretler.forEach(x => x.remove()); isaretler = [];
    if (!modAcik() || IZOLE || PAGE === "sunum") return;
    const st = durumAl();
    oku().slaytlar.forEach((s, si) => s.ogeler.forEach(o => {
      if (o.sayfa !== SAYFA || !o.konum || !buDurumda(o, st)) return;
      const el = bul(o.konum); if (!el || !el.offsetParent) return;
      const r = el.getBoundingClientRect(), sx = scrollX, sy = scrollY;
      const c = Object.assign(document.createElement("div"), { className: "ss-cerceve ss-ui" });
      Object.assign(c.style, { left: r.left + sx - 3 + "px", top: r.top + sy - 3 + "px", width: r.width + 6 + "px", height: r.height + 6 + "px" });
      const z = Object.assign(document.createElement("div"), { className: "ss-rozet ss-ui", textContent: `✓ Slayt ${si + 1}${s.ogeler.length > 1 ? ` · ${s.ogeler.indexOf(o) + 1}/${s.ogeler.length}` : ""}` });
      Object.assign(z.style, { left: r.right + sx + 3 - 70 + "px", top: r.top + sy - 3 + "px" });
      document.body.append(c, z); isaretler.push(c, z);
      requestAnimationFrame(() => { z.style.left = r.right + sx + 3 - z.offsetWidth + "px"; });
    }));
  }
  let isT; const isaretleSonra = () => { clearTimeout(isT); isT = setTimeout(isaretle, 160); };
  function toast(m) {
    let t = document.querySelector(".ss-toast"); if (!t) { stilEkle(); t = Object.assign(document.createElement("div"), { className: "ss-toast ss-ui" }); document.body.appendChild(t); }
    t.textContent = m; t.classList.add("on"); clearTimeout(t._z); t._z = setTimeout(() => t.classList.remove("on"), 1600);
  }

  // ---- ekran görüntüsü: sabit resim olarak eklenir (sayfa güncellense de değişmez)
  let kirpAcik = false;
  const sayfaZemin = () => { for (const e of [document.body, document.documentElement]) { const c = getComputedStyle(e).backgroundColor; if (c && !/rgba\(0, 0, 0, 0\)|transparent/.test(c)) return c; } return "#ffffff"; };
  function svgSabitle(kok) {   // SVG çizimlerindeki sınıf stilleri görüntüye geçsin
    $$("svg *", kok).forEach(n => {
      if (!(n instanceof SVGElement) || /^(defs|clipPath|linearGradient|radialGradient|stop|title|desc)$/i.test(n.tagName)) return;
      const cs = getComputedStyle(n);
      ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity", "fill-opacity", "stroke-opacity", "font-family", "font-size", "font-weight", "text-anchor", "dominant-baseline"].forEach(k => {
        const v = cs.getPropertyValue(k); if (v && !n.style.getPropertyValue(k)) n.style.setProperty(k, v);
      });
      if (cs.display === "none" || cs.visibility === "hidden") n.style.setProperty("display", "none");
    });
  }
  async function fotoEkle(url, w, h, ad, ayni) {
    const o = { id: uid(), tur: "goruntu", sayfa: SAYFA, ad, yolAd: yolAd(), w: Math.round(w), h: Math.round(h), cekim: Date.now(), t: Date.now() };
    await idb.set("resim", o.id, url);
    const d = ekle(o, ayni); toast(`📷 Ekran görüntüsü eklendi · Slayt ${slaytNo(d, d.sonSlayt)}`); isaretle();
  }
  async function fotoAlan(el, ayni) {
    toast("Görüntü alınıyor…");
    try {
      const H = await libYukle("html-to-image.js", "htmlToImage"); svgSabitle(el);
      const r = el.getBoundingClientRect(), w = Math.ceil(r.width), h = Math.ceil(r.height);
      const op = { pixelRatio: 2, width: w, height: h, backgroundColor: sayfaZemin(), cacheBust: false, filter: n => !(n.classList && (n.classList.contains("tip") || n.classList.contains("ss-ui"))) };
      let url; try { url = await H.toPng(el, op); } catch (e) { url = await H.toPng(el, { ...op, skipFonts: true }); }
      await fotoEkle(url, w, h, "📷 " + (baslik(el) || "Ekran görüntüsü"), ayni);
    } catch (e) { toast("Görüntü alınamadı: " + e.message); }
  }
  // kaydırılmış sayfada ekrana yapışık duran öğeler (ör. soldaki konu listesi) görüntüde de o anki yerinde çizilsin
  function yapiskanSabitle() {
    const geri = [];
    $$("body *").forEach(e => {
      if (e.closest(".ss-ui") || getComputedStyle(e).position !== "sticky") return;
      const r1 = e.getBoundingClientRect(), es = { p: e.style.position, t: e.style.top, l: e.style.left, b: e.style.bottom };
      e.style.position = "relative"; e.style.top = "0px"; e.style.left = "0px"; e.style.bottom = "auto";
      const r0 = e.getBoundingClientRect();
      e.style.top = (r1.top - r0.top) + "px"; e.style.left = (r1.left - r0.left) + "px";
      geri.push(() => { e.style.position = es.p; e.style.top = es.t; e.style.left = es.l; e.style.bottom = es.b; });
    });
    return () => geri.forEach(f => f());
  }
  async function bolgeAl(r, ayni) {
    toast("Görüntü alınıyor…");
    let coz = () => {};
    try {
      coz = yapiskanSabitle();
      const H = await libYukle("html-to-image.js", "htmlToImage"), B = document.body, br = B.getBoundingClientRect(); svgSabitle(B);
      const x = r.left - br.left, y = r.top - br.top;
      const op = { pixelRatio: 2, width: Math.round(r.width), height: Math.round(r.height), backgroundColor: sayfaZemin(), cacheBust: false,
        style: { width: B.scrollWidth + "px", height: B.scrollHeight + "px", margin: "0", transform: `translate(${-x}px, ${-y}px)`, transformOrigin: "0 0" },
        filter: n => !(n.classList && (n.classList.contains("tip") || n.classList.contains("ss-ui"))) };
      let url; try { url = await H.toPng(B, op); } catch (e) { url = await H.toPng(B, { ...op, skipFonts: true }); }
      coz(); coz = () => {};
      const yol = yolAd().split(" › ");
      await fotoEkle(url, r.width, r.height, "📷 " + (yol[yol.length - 1] || "Ekran görüntüsü"), ayni);
    } catch (e) { toast("Görüntü alınamadı: " + e.message); }
    finally { coz(); }
  }
  function kirp(ayni) {
    if (kirpAcik) return; stilEkle(); kirpAcik = true;
    if (hl) { hl.style.display = et.style.display = "none"; kilit = false; }
    const ov = Object.assign(document.createElement("div"), { className: "ss-kirp ss-ui" });
    ov.innerHTML = `<div class="ip">✂ Görüntüsünü almak istediğiniz bölgeyi fareyle çizin · Esc: vazgeç</div><div class="kutu"></div>`;
    document.body.appendChild(ov);
    const k = ov.querySelector(".kutu"); let x0, y0, r = null;
    const bitir = () => { kirpAcik = false; ov.remove(); removeEventListener("keydown", esc_, true); };
    const esc_ = e => { if (e.key === "Escape") { e.preventDefault(); bitir(); } };
    addEventListener("keydown", esc_, true);
    ov.addEventListener("pointerdown", e => { e.preventDefault(); x0 = e.clientX; y0 = e.clientY; ov.setPointerCapture(e.pointerId); k.style.display = "block"; r = null; });
    ov.addEventListener("pointermove", e => { if (x0 == null) return; r = { left: Math.min(x0, e.clientX), top: Math.min(y0, e.clientY), width: Math.abs(e.clientX - x0), height: Math.abs(e.clientY - y0) };
      Object.assign(k.style, { left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px" }); });
    ov.addEventListener("pointerup", () => { const rr = r; bitir(); if (rr && rr.width > 20 && rr.height > 20) bolgeAl(rr, ayni || ctrl); else toast("Bölge çok küçük"); });
  }
  // en içteki görünür sayfa (ör. Bankacılık › TCMB › Rezervler iç sayfası) — çubuktaki düğme oradan görüntü alır
  function icSayfa() {
    let w = window;
    for (let i = 0; i < 4; i++) {
      let f = null; try { f = [...w.document.querySelectorAll("iframe")].filter(x => { const r = x.getBoundingClientRect(); return !x.hidden && r.width > 300 && r.height > 200; }).sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0]; } catch (e) {}
      if (!f) break; try { if (!f.contentWindow.alcoSunum) break; w = f.contentWindow; } catch (e) { break; }
    }
    return w;
  }

  // alt çubuk (en üst pencerede)
  let bar;
  function barCiz() {
    if (!UST || IZOLE || PAGE === "sunum") return;
    if (!modAcik()) { if (bar) bar.remove(); bar = null; return; }
    stilEkle();
    if (!bar) { bar = Object.assign(document.createElement("div"), { className: "ss-bar ss-ui" }); document.body.appendChild(bar);
      bar.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return;
        if (b.dataset.a === "kirp") { const w = icSayfa(); try { (w.alcoSunum || api).kirp(); } catch (er) { kirp(); } return; }
        if (b.dataset.a === "bitti") api.bitir(); else if (b.dataset.a === "ac") api.ac(); else if (b.dataset.a === "geri") { const d = oku(), o = ogeler(d).sort((a, b) => b.t - a.t)[0]; if (o) { cikar(o.id); toast("Son eklenen çıkarıldı"); } } }); }
    const d = oku(), n = ogeler(d).length;
    bar.innerHTML = `<span class="nokta"></span><span class="ip"><b style="color:#fff">Seçim modu</b> · Alanın üzerine gelip <b style="color:#fff">＋ Sunuma ekle</b> ya da <b style="color:#fff">📷 Ekran görüntüsü</b>; her ekleme yeni slayt olur. <b style="color:#fff">Ctrl</b> basılıyken eklenen önceki slayta girer.</span>
      <span class="say">${n} alan · ${d.slaytlar.length} slayt</span><button data-a="kirp" title="Sayfada istediğiniz bölgeyi çizerek ekran görüntüsü alın">✂ Ekran görüntüsü</button><button data-a="geri" ${n ? "" : "disabled"} title="Son ekleneni çıkar">↶</button><button class="ana" data-a="ac">Sunumu hazırla →</button><button data-a="bitti">Bitti</button>`;
  }

  function modDegisti() {
    document.documentElement.classList.toggle("ss-mod", modAcik() && !IZOLE && PAGE !== "sunum");
    if (modAcik() && !IZOLE && PAGE !== "sunum") uiKur(); else if (hl) { hl.style.display = et.style.display = "none"; aday = []; }
    barCiz(); isaretle(); dugmeGuncelle();
  }

  // ---- üst başlıktaki "Sunum" düğmesi ve menü
  function dugmeGuncelle() {
    const n = ogeler(oku()).length;
    const b = document.getElementById("atSunum"); if (!b) return;
    b.innerHTML = `▣ Sunum${n ? ` <span style="font-family:'DM Mono',ui-monospace,monospace;background:var(--at-red,#c8102e);color:#fff;border-radius:8px;padding:1px 6px;font-size:11px;margin-left:3px">${n}</span>` : ""}`;
    b.setAttribute("aria-pressed", modAcik() ? "true" : "false");
  }
  function menu(cap) {
    stilEkle();
    const eski = document.querySelector(".ss-pop"); if (eski) { eski.remove(); return; }
    const p = Object.assign(document.createElement("div"), { className: "ss-pop ss-ui" });
    const n = ogeler(oku()).length;
    p.innerHTML = `<button data-a="mod"><i>${modAcik() ? "■" : "✚"}</i>${modAcik() ? "Seçim modunu kapat" : "Tıklayarak alan seç"}<small>${modAcik() ? "Seçtikleriniz taslakta kalır" : "Sitedeki grafik, tablo ve kartları sunuma ekleyin"}</small></button>
      <button data-a="ac"><i>▶</i>Sunumu düzenle ve başlat<small>${n ? `${n} alan seçili · sıralama, not, PDF, PowerPoint` : "Katalogdan ya da şablondan da başlayabilirsiniz"}</small></button>
      <button data-a="sablon"><i>☰</i>Şablondan oluştur<small>Örn. APKO Haftalık — güncel verilerle hazır</small></button>
      ${n ? `<hr><button data-a="yeni"><i>⟲</i>Yeni sunum<small>Seçili ${n} alanı temizle</small></button>` : ""}
      <hr><button data-a="ana"><i>⌂</i>Sunum ana sayfası<small>Slaytlar, kayıtlı sunumlar ve şablonlar</small></button>`;
    document.body.appendChild(p);
    const r = cap.getBoundingClientRect();
    p.style.top = r.bottom + scrollY + 6 + "px";
    p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, r.right + scrollX - p.offsetWidth)) + "px";
    p.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; e.stopPropagation(); p.remove();
      if (b.dataset.a === "mod") modAcik() ? api.bitir() : api.basla();
      if (b.dataset.a === "ac" || b.dataset.a === "ana") api.ac();
      if (b.dataset.a === "sablon") api.ac("sablon");
      if (b.dataset.a === "yeni" && confirm("Sunum taslağındaki tüm slaytlar silinsin mi?")) { yaz(yeniSunum()); toast("Taslak temizlendi"); } });
    setTimeout(() => document.addEventListener("click", function k(e) { if (!p.contains(e.target)) { p.remove(); document.removeEventListener("click", k); } }), 0);
  }
  function ustDugme() {
    const pdf = document.getElementById("atPdf"); if (!pdf || document.getElementById("atSunum")) return;
    const b = Object.assign(document.createElement("button"), { type: "button", className: "at-btn", id: "atSunum", title: "Sitedeki alanlardan sunum oluştur" });
    pdf.parentElement.insertBefore(b, pdf);
    b.addEventListener("click", e => { e.stopPropagation(); menu(b); });
    dugmeGuncelle();
  }

  // ---- izole gösterim (Sunum sayfasındaki slaytlar)
  let hedef = null, izOge = null, hedefler = [], kokGen = 0, genZorla = +Q.get("gen") || 0;
  // slaytta kenardan uzatma: Sunum sayfası alanın sayfa içindeki genişliğini değiştirir (ssGen), sayfa o genişlikte yeniden çizer.
  // Bazı sayfalar yalnızca pencere genişliği değişince yeniden çizer; bunun için innerWidth'e küçük bir sapma eklenip resize tetiklenir.
  let iwEk = 0;
  if (IZOLE) try { const d = Object.getOwnPropertyDescriptor(window, "innerWidth"); if (d && d.get) Object.defineProperty(window, "innerWidth", { configurable: true, enumerable: true, get() { return d.get.call(window) + iwEk; } }); } catch (e) {}
  const yenidenCiz = () => { iwEk = iwEk ? 0 : 64; dispatchEvent(new Event("resize")); };
  function genUygula() {
    if (!hedef) return;
    const gen = genZorla || (hedefler.length > 1 ? kokGen : izOge && (izOge.w || (izOge.ogeler && izOge.ogeler.length === 1 && izOge.ogeler[0].w)));
    if (gen) hedef.style.setProperty("width", Math.max(200, gen) + "px", "important"); else hedef.style.removeProperty("width");
  }
  // ayrı gösterilen alanlar: kullanıcı bu alanda bir şeye (kutucuk, sekme) tıklayınca durum Sunum sayfasına bildirilir; o da aynı sayfadan gelen diğer alanlara uygular
  if (IZOLE) document.addEventListener("click", e => { if (!e.isTrusted || !hedef) return; setTimeout(() => { try { parent.postMessage({ ssDurum: 1, id: Q.get("sunum"), durum: durumAl() }, location.origin); } catch (x) {} }, 350); }, true);
  if (IZOLE) addEventListener("message", e => { const m = e.data; if (m && e.origin === location.origin && m.ssDurumUygula) durumUygula(m.ssDurumUygula).then(() => { setTimeout(haber, 300); }).catch(() => {}); });
  if (IZOLE) addEventListener("message", e => { const m = e.data; if (m && e.origin === location.origin && m.ssYorumIste) { sonYorum = ""; yorumGonder(); } });
  // grafiğin üzerinde gezinirken açılan ipucu kutuları alanı büyütmesin (slayt sürekli yeniden çizilip kasmasın)
  let etkilesim = false;
  if (IZOLE) document.addEventListener("pointermove", () => { etkilesim = true; }, { capture: true, passive: true });
  if (IZOLE) addEventListener("message", e => {
    const m = e.data; if (!m || e.origin !== location.origin || m.ssGen == null) return;
    const g = Math.round(+m.ssGen) || 0; if (g === genZorla) return;
    genZorla = g; genUygula(); yenidenCiz(); setTimeout(haber, 60); yorumPlan(400);
  });
  const ortakAta = els => { let a = els[0]; while (a && !els.every(e => a.contains(e))) a = a.parentElement; return a && a !== document.body && a !== document.documentElement ? a : els[0]; };
  async function izole(o) {
    izOge = o;
    const L = o.ogeler && o.ogeler.length ? o.ogeler : [o], durum = o.durum || L[0].durum;
    const t = Q.get("tema");
    const root = document.documentElement;
    root.classList.add("ss-izole");
    if (t) {
      const once = ["alco-theme", "fd-theme", "bv.theme"].map(k => [k, ls.get(k)]);
      const koyu = () => root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      if (SAYFA === "tefas.html") { const thm = document.getElementById("thm"); if (thm && (t === "dark") !== koyu()) thm.click(); }
      root.dataset.theme = t; once.forEach(([k, v]) => ls.set(k, v));
    }
    if (window.Chart && window.Chart.defaults) try { window.Chart.defaults.animation = false; } catch (e) {}
    const st = document.createElement("style"); st.textContent = `
html.ss-izole,html.ss-izole body{background:transparent!important;margin:0!important;padding:0!important;overflow:hidden!important;min-height:0!important;height:auto!important}
html.ss-izole [data-ss-gizle]{display:none!important}
html.ss-izole [data-ss-yol]{display:block!important;padding:0!important;margin:0!important;border:0!important;max-width:none!important;width:auto!important;min-width:0!important;min-height:0!important;height:auto!important;max-height:none!important;box-shadow:none!important;background:transparent!important;position:static!important;transform:none!important;overflow:visible!important;columns:auto!important}
html.ss-izole [data-ss-hedef]{margin:0!important;width:100%!important;max-width:none!important;position:relative!important;inset:auto!important;transform:none!important;box-sizing:border-box!important;max-height:none!important;cursor:default!important}
html.ss-izole [data-ss-hedef].kc .t span:last-child{display:none!important}
html.ss-izole .tw,html.ss-izole [data-ss-hedef] .tw{overflow:visible!important}
html.ss-izole #alcoTop,html.ss-izole .ss-bar,html.ss-izole #alcoPrintHead{display:none!important}`;
    document.head.appendChild(st);
    // sayfa yüklenip ilk içerik çizilene kadar bekle (sekme düğmelerine veri gelmeden basılmasın)
    await new Promise(r => document.readyState === "complete" ? r() : addEventListener("load", r, { once: true }));
    for (let i = 0; i < 50; i++) { if ($$(".card,.kc,article,.box,.panel,.tkp,.chartbox").some(e => e.getBoundingClientRect().height > 40)) break; await bekle(200); }
    await bekle(250);
    // sayfa verisi gelene ve alan bulunana kadar dene
    const t0 = Date.now(); let onceki = "", sabit = 0, el = null, els = [];
    while (Date.now() - t0 < 30000) {
      const deg = await durumUygula(durum);
      els = L.map(x => bul(x.konum)).filter(Boolean); el = els.length ? ortakAta(els) : null;
      const r = el && el.getBoundingClientRect(), olcu = r ? Math.round(r.width) + "x" + Math.round(r.height) + ":" + els.length : "";
      if (el && r.height > 20 && !deg && olcu === onceki && (els.length === L.length || Date.now() - t0 > 8000)) { if (++sabit >= 2) break; } else sabit = 0;
      onceki = olcu; await bekle(350);
    }
    if (el && els.length > 1) kokGen = Math.round(el.getBoundingClientRect().width);     // grubun sitedeki genişliği
    if (!el) { document.body.innerHTML = `<div style="font:14px system-ui;color:#888;padding:30px;text-align:center">Bu alan sayfada bulunamadı: <b>${esc(o.ad || L.map(x => x.ad).join(", "))}</b><br>Sayfa yapısı değişmiş olabilir; slaytı silip alanı yeniden ekleyin.</div>`; root.classList.remove("ss-izole"); haber({ hata: 1, w: 500, h: 120 }); return; }
    yerlestir(els);
    // sayfa kendini yeniden çizerse (ör. kutucuğa tıklanınca grafik değişir) alanları yeniden bul
    let mt; new MutationObserver(() => {
      if (hedef && hedef.isConnected && hedefler.every(x => x.isConnected)) return;
      clearTimeout(mt); mt = setTimeout(() => { const y = L.map(x => bul(x.konum)).filter(Boolean); if (y.length) yerlestir(y); }, 30);
    }).observe(document.body, { childList: true, subtree: true });
  }
  let ro;
  const korunur = s => /^(SCRIPT|STYLE|LINK)$/.test(s.tagName) || s.classList.contains("tip") || s.classList.contains("tt");
  function yerlestir(els) {
    if (!Array.isArray(els)) els = [els];
    $$("[data-ss-gizle]").forEach(x => x.removeAttribute("data-ss-gizle")); $$("[data-ss-yol]").forEach(x => x.removeAttribute("data-ss-yol"));
    if (hedef) hedef.removeAttribute("data-ss-hedef");
    const el = ortakAta(els);
    hedef = el; hedefler = els; el.setAttribute("data-ss-hedef", "");
    genUygula();
    // alanın üstündeki sarmalayıcılar sadeleşir, yanındaki her şey gizlenir
    for (let x = el; x && x !== document.body; x = x.parentElement) {
      if (x !== el) x.setAttribute("data-ss-yol", "");
      for (const s of x.parentElement ? x.parentElement.children : []) if (s !== x && !korunur(s)) s.setAttribute("data-ss-gizle", "");
    }
    // birden çok alan: ortak kabın içindeki seçilmemiş kart ve grafikler gizlenir; sitedeki yerleşim (ve aradaki küçük işaretler) korunur
    if (els.length > 1) {
      const yolda = new Set(); els.forEach(e => { for (let x = e; x && x !== el; x = x.parentElement) yolda.add(x); });
      yolda.forEach(x => { for (const s of x.parentElement.children) if (!yolda.has(s) && !korunur(s) && (blokMu(s) || s.querySelector(BLOK) || s.getBoundingClientRect().height > 90)) s.setAttribute("data-ss-gizle", ""); });
    }
    dispatchEvent(new Event("resize"));
    if (ro) ro.disconnect();
    ro = new ResizeObserver(() => haber()); ro.observe(el);
    setTimeout(haber, 50); yorumPlan(1200); setTimeout(() => yorumPlan(0), 4000);     // grafik geç çizilirse bir kez daha
  }

  // ---- grafik yorumu: alandaki grafiklerin verisinden kısa, sayıya dayalı yorum (slaytın "Öne çıkanlar" satırlarına gider)
  // Sayfalar grafiği çizerken verisini kaba bırakır (el._ssSeri); TEFAS'taki Chart.js grafikleri doğrudan okunur.
  let yorumT = 0, yorumIlk = 0, sonYorum = "";
  // sayfa sürekli değişse de (saat, kayan yazı) en geç ~2 sn'de bir yorum gönderilir
  const yorumPlan = ms => { const t = Date.now(); if (yorumT && t - yorumIlk > 1500) return; if (!yorumT) yorumIlk = t; clearTimeout(yorumT); yorumT = setTimeout(() => { yorumT = 0; yorumGonder(); }, ms); };
  const sayi = (v, d) => v == null || !isFinite(v) ? "—" : v.toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d });
  const AYK = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
  function tarihAl(x) {
    if (x instanceof Date) return isNaN(x) ? null : x;
    if (typeof x === "number") return x > 1e11 ? new Date(x) : null;
    const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(String(x || "")); return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +(m[3] || 1))) : null;
  }
  const tarihYaz = (x, gunlu) => { const d = tarihAl(x); if (!d) return String(x ?? ""); return (gunlu ? d.getUTCDate() + " " : "") + AYK[d.getUTCMonth()] + " " + d.getUTCFullYear(); };
  function serilerTopla() {
    if (!hedef) return [];
    const L = [];
    [hedef, ...hedef.querySelectorAll("*")].forEach(n => { if (n._ssSeri && n.isConnected && n.getClientRects().length) L.push(n._ssSeri); });
    const C = window.Chart;
    if (C && C.getChart) hedef.querySelectorAll("canvas").forEach(cv => {
      const ch = C.getChart(cv); if (!ch || !cv.getClientRects().length) return;
      const lab = ch.data.labels || [];
      const tip = ch.config.type, seri = ch.data.datasets.filter(d => !d.hidden && ch.isDatasetVisible(ch.data.datasets.indexOf(d))).map(d => ({ ad: d.label || "", p: d.data.map((v, i) => typeof v === "object" && v ? [v.x, v.y] : [lab[i], v]) }));
      if (tip === "doughnut" || tip === "pie") L.push({ pasta: 1, baslik: ch.options?.plugins?.title?.text || "", dilim: lab.map((l, i) => [l, ch.data.datasets[0]?.data[i]]) });
      else L.push({ seriler: seri });
    });
    return L;
  }
  function seriYorum(S, baslik) {
    if (S.pasta) {      // dağılım: en büyük iki dilim
      const t = S.dilim.reduce((a, d) => a + (+d[1] || 0), 0); if (!t) return [];
      const D = S.dilim.filter(d => +d[1] > 0).sort((a, b) => b[1] - a[1]).slice(0, 3);
      return [`Dağılımda <b>${esc(D[0][0])}</b> %${sayi(D[0][1] / t * 100, 1)} payla ilk sırada` + (D[1] ? `; ardından ${esc(D[1][0])} (%${sayi(D[1][1] / t * 100, 1)})` + (D[2] ? ` ve ${esc(D[2][0])} (%${sayi(D[2][1] / t * 100, 1)})` : "") : "") + " geliyor."];
    }
    const out = [];
    const ss = (S.seriler || []).map(x => ({ ...x, p: (x.p || []).filter(q => q && q[1] != null && isFinite(q[1])) })).filter(x => x.p.length >= 2);
    ss.slice(0, 2).forEach(x => {
      const P = x.p, n = P.length, son = P[n - 1], onc = P[n - 2], v = +son[1];
      const ad = (x.ad || S.baslik || baslik || "Seri").replace(/\s+/g, " ").trim();
      const ipucu = (S.birim || "") + " " + ad + " " + (S.baslik || "") + " " + (baslik || "");
      const fmt = x.fmt || S.fmt;
      const birim = S.birim && !/%|değişim|endeks/i.test(S.birim) ? " " + S.birim : "";
      const deger = q => { try { if (fmt) return String(fmt(q)).replace(/<[^>]+>/g, "") + (/[a-zA-Z₺$€%]/.test(String(fmt(q))) ? "" : birim); } catch (e) {} return sayi(q, Math.abs(q) >= 1000 ? 0 : Math.abs(q) >= 100 ? 1 : 2) + birim; };
      const bp = /\bbp\b|baz puan|CDS/i.test(ipucu), oran = bp || /%|faiz|oran|getiri|enflasyon|TÜFE|ÜFE|beklenti|büyüme|kâr payı|swap|değişim/i.test(ipucu) || /%/.test(deger(v));
      const fark = (a, b) => {
        if (b == null || !isFinite(b)) return "";
        if (bp) { const d = a - b; return `${d > 0 ? "+" : d < 0 ? "−" : "±"}${sayi(Math.abs(d), 0)} bp`; }
        if (oran) { const d = a - b; return Math.abs(d) < .005 ? "değişmedi" : `${d > 0 ? "+" : "−"}${sayi(Math.abs(d), 2)} puan`; }
        if (!b) return ""; const r = (a / b - 1) * 100; return Math.abs(r) < .05 ? "yatay" : `${r > 0 ? "+" : "−"}%${sayi(Math.abs(r), 1)}`;
      };
      const dS = tarihAl(son[0]), gunlu = dS && P.length > 2 && (() => { const d0 = tarihAl(P[n - 2][0]); return d0 && (dS - d0) < 20 * 864e5; })();
      let yil = null, ybb = null;
      if (dS) {
        const hedefT = new Date(dS); hedefT.setUTCFullYear(dS.getUTCFullYear() - 1);
        for (let i = n - 1; i >= 0; i--) { const d = tarihAl(P[i][0]); if (!d) break; if (!ybb && d.getUTCFullYear() < dS.getUTCFullYear()) ybb = P[i]; if (d <= hedefT) { if (hedefT - d < 45 * 864e5) yil = P[i]; break; } }
      }
      const parca = [];
      const f1 = fark(v, +onc[1]); if (f1) parca.push(`bir önceki ${gunlu ? "veriye" : "döneme"}${tarihAl(onc[0]) ? " (" + tarihYaz(onc[0], gunlu) + ")" : ""} göre ${f1}`);
      if (ybb && ybb !== onc) { const f = fark(v, +ybb[1]); if (f) parca.push(`yılbaşından bu yana ${f}`); }
      if (yil && yil !== onc && yil !== ybb) { const f = fark(v, +yil[1]); if (f) parca.push(`bir yılda ${f}`); }
      let ek = "";
      const V = P.map(q => +q[1]), mx = Math.max(...V), mn = Math.min(...V);
      if (n >= 6 && v === mx && mx !== mn) ek = " Grafikteki dönemin en yüksek seviyesinde.";
      else if (n >= 6 && v === mn && mx !== mn) ek = " Grafikteki dönemin en düşük seviyesinde.";
      let seri = 0, yon = Math.sign(V[n - 1] - V[n - 2]); for (let i = n - 1; i > 0 && yon && Math.sign(V[i] - V[i - 1]) === yon; i--) seri++;
      if (seri >= 3) ek += ` Üst üste ${seri} ${gunlu ? "veridir" : "dönemdir"} ${yon > 0 ? "artıyor" : "geriliyor"}.`;
      out.push(`<b>${esc(ad)}</b>${dS ? " " + tarihYaz(son[0], gunlu) : son[0] != null && typeof son[0] !== "number" ? " (" + esc(son[0]) + ")" : ""} itibarıyla <b>${esc(deger(v))}</b>${parca.length ? "; " + parca.join(", ") : ""}.${ek}`);
    });
    return out;
  }
  function yorumGonder() {
    if (!hedef || !IZOLE) return;
    let satir = [];
    try { serilerTopla().forEach(S => { satir.push(...seriYorum(S, baslik(hedef))); }); } catch (e) { satir = []; }
    satir = [...new Set(satir)].slice(0, 3);
    const k = satir.join("|"); if (k === sonYorum) return; sonYorum = k;
    try { parent.postMessage({ ssYorum: 1, id: Q.get("sunum"), satirlar: satir }, location.origin); } catch (e) {}
  }
  let sonOlcu = "";
  let sonW = 0, sonH = 0;
  function haber(x) {
    const r = hedef ? hedef.getBoundingClientRect() : null;
    let w = r ? Math.max(r.width, hedef.scrollWidth) : 0, h = r ? Math.max(r.height, hedef.scrollHeight) : 0;
    if (r && etkilesim) { w = Math.max(r.width, Math.min(w, sonW || r.width)); h = Math.max(r.height, Math.min(h, sonH || r.height)); }     // taşma yalnız ilk ölçümde
    if (!x) { sonW = w; sonH = h; }
    const m = x || { w: Math.ceil(w), h: Math.ceil(h) };
    const k = m.w + "x" + m.h + (m.hata ? "!" : ""); if (k === sonOlcu) return; sonOlcu = k;
    try { parent.postMessage({ ssBoyut: 1, id: Q.get("sunum"), ...m }, location.origin); } catch (e) {}
  }

  // yakalama: dışa aktarma için alanın PNG görüntüsü
  const libYukle = (ad, glob) => window[glob] ? Promise.resolve(window[glob]) : new Promise((ok, no) => {
    const s = document.createElement("script"); s.src = new URL("ortak/lib/" + ad, KOK).href; s.onload = () => ok(window[glob]); s.onerror = () => no(new Error(ad + " yüklenemedi")); document.head.appendChild(s); });
  async function yakala(pr = 2) {
    if (!hedef) throw new Error("alan yok");
    try { yorumGonder(); } catch (e) {}       // dışa aktarmada öne çıkanlar güncel grafikle aynı olsun
    const H = await libYukle("html-to-image.js", "htmlToImage");
    // SVG çizimlerinde sınıfla verilen stiller (fill:none gibi) görüntüye geçsin diye hesaplanmış değerleri öğeye yaz
    $$("svg *", hedef).forEach(n => {
      if (!(n instanceof SVGElement) || /^(defs|clipPath|linearGradient|radialGradient|stop|title|desc)$/i.test(n.tagName)) return;
      const cs = getComputedStyle(n);
      ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity", "fill-opacity", "stroke-opacity", "font-family", "font-size", "font-weight", "text-anchor", "dominant-baseline"].forEach(k => {
        const v = cs.getPropertyValue(k); if (v && !n.style.getPropertyValue(k)) n.style.setProperty(k, v);
      });
      if (cs.display === "none" || cs.visibility === "hidden") n.style.setProperty("display", "none");
    });
    const r = hedef.getBoundingClientRect(), w = Math.ceil(Math.max(r.width, hedef.scrollWidth)), h = Math.ceil(Math.max(r.height, hedef.scrollHeight));
    const op = { pixelRatio: pr, width: w, height: h, cacheBust: false, filter: n => !(n.classList && (n.classList.contains("tip") || n.classList.contains("ss-ui"))) };
    let url;
    try { url = await H.toPng(hedef, op); } catch (e) { url = await H.toPng(hedef, { ...op, skipFonts: true }); }
    return { url, w, h };
  }

  // ---- dışa açık arayüz
  const api = window.alcoSunum = {
    oku, yaz, yeniSunum, ekle, cikar, bul, durumAl, durumUygula, konum, baslik, norm, ogeYap, uid, kucukMu,
    sayfa: SAYFA, kok: KOK.href,
    dinle: f => { dinleyici.add(f); return () => dinleyici.delete(f); },
    basla() { ls.set(KM, "1"); modDegisti(); try { top.alcoSunum && top !== window && top.alcoSunum._yenile(); } catch (e) {} },
    bitir() { ls.set(KM, null); modDegisti(); try { top.alcoSunum && top !== window && top.alcoSunum._yenile(); } catch (e) {} },
    ac(hash) {
      const u = new URL("sunum/", KOK).href + (hash ? "#" + hash : "");
      let w = null; try { w = (top || window).open(u, "alco-sunum"); } catch (e) {}
      if (!w) location.href = u; else try { w.focus(); } catch (e) {}
    },
    yorumlar: () => hedef ? serilerTopla().flatMap(S => seriYorum(S, baslik(hedef))) : [],
    menu, modAcik, _yenile: modDegisti, _yolAd: () => yolAd(), idb, kirp, fotoAlan,
    yakala, hazir: null
  };

  // ---- başlat
  dinleyici.add(() => { barCiz(); isaretleSonra(); dugmeGuncelle(); if (hl && aday[0]) ciz(); });
  if (IZOLE) {
    api.hazir = new Promise(ok => {
      const basla = () => { const o = (() => { try { return parent.alcoSunumOge && parent.alcoSunumOge(Q.get("sunum")); } catch (e) { return null; } })();
        if (!o) { ok(false); return; } izole(o).then(() => { setTimeout(() => ok(true), 400); }); };
      document.readyState === "loading" ? addEventListener("DOMContentLoaded", basla) : basla();
    });
    return;
  }
  const kur = () => {
    if (UST && PAGE !== "sunum") ustDugme();
    dugmeGuncelle();
    document.addEventListener("mousemove", hareket, { passive: true });
    addEventListener("keydown", e => { if (e.key === "Control" || e.key === "Meta") ctrlAyarla(true); });
    addEventListener("keyup", e => { if (e.key === "Control" || e.key === "Meta") ctrlAyarla(false); });
    addEventListener("blur", () => ctrlAyarla(false));
    addEventListener("scroll", () => { if (modAcik()) { if (aday[0] && hl) ciz(); } }, { passive: true, capture: true });
    addEventListener("resize", isaretleSonra);
    document.addEventListener("click", e => { if (modAcik() && !e.target.closest(".ss-ui")) isaretleSonra(); }, true);
    addEventListener("hashchange", isaretleSonra);
    modDegisti();
    // sayfa verisi geldikten sonra işaretleri yenile
    setTimeout(isaretle, 1500); setTimeout(isaretle, 4000);
  };
  document.readyState === "loading" ? addEventListener("DOMContentLoaded", kur) : kur();
})();
