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
    if (!t) t = metin(ilk("b,strong,th,.k,.lbl,.nm"));
    if (!t) t = metin(el).slice(0, 50);
    return t.replace(/\s*(Detay →|↗)\s*$/, "").slice(0, 90);
  }

  // ---- sunum taslağı (localStorage)
  const yeniSunum = () => ({ v: 1, ad: "", tema: "light", kapak: { goster: true, baslik: "Haftalık Piyasa Değerlendirmesi", alt: "Aktif Pasif Yönetimi" },
    gundem: { goster: true }, kapanis: { goster: true, baslik: "Teşekkürler", alt: "" }, slaytlar: [] });
  const oku = () => { try { const d = JSON.parse(ls.get(K)); if (d && Array.isArray(d.slaytlar)) return d; } catch (e) {} return yeniSunum(); };
  const dinleyici = new Set();
  const yaz = d => { d.degisti = Date.now(); ls.set(K, JSON.stringify(d)); dinleyici.forEach(f => { try { f(d); } catch (e) {} }); };
  addEventListener("storage", e => { if (e.key === K) dinleyici.forEach(f => { try { f(oku()); } catch (x) {} }); if (e.key === KM) modDegisti(); });
  const ogeler = d => d.slaytlar.flatMap(s => s.ogeler);

  // otomatik düzen: küçük göstergeler (Özet kartları gibi) aynı sayfadan geliyorsa tek slaytta toplanır (en çok 6)
  const kucukMu = o => o.w * o.h < 70000 || (o.w < 330 && o.h < 260);
  function ekle(o) {
    const d = oku(); o.kucuk = kucukMu(o);
    const son = d.slaytlar[d.slaytlar.length - 1];
    if (o.kucuk && son && son.ogeler.length < 6 && son.ogeler.every(x => x.kucuk && x.sayfa === o.sayfa && x.yolAd === o.yolAd) && !son.kilit) son.ogeler.push(o);
    else d.slaytlar.push({ id: uid(), baslik: o.kucuk ? (o.yolAd.split(" › ").pop() || o.ad) : o.ad, not: "", oc: null, kaynak: null, duzen: "oto", ogeler: [o] });
    yaz(d); return d;
  }
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
  function durumAl() {
    const b = [];
    $$(DUGME).forEach(x => { if (x.closest("#alcoTop,.ss-ui")) return; const g = grupOf(x); if (!g || g === document.body) return;
      b.push({ g: g.id, k: anahtar(x), v: durumu(x), sek: x.getAttribute("role") === "tab" || x.hasAttribute("aria-selected") || SEKME_GRUP.test(g.id) }); });
    const s = $$("select[id]").filter(x => !x.closest(".ss-ui")).map(x => ({ s: x.id, v: x.value }));
    return { b, s, h: location.hash };
  }
  // durum imzası: alt sekmeler + alanın kendi içindeki düğmeler (ör. BDDK kartında TL kredi / TL mevduat)
  const imza = (st, ic) => (st.b || []).filter(x => x.v && (x.sek || !ic || ic.includes(x.g))).map(x => x.g + ":" + x.k).sort().join("|") + "#" + (st.s || []).filter(x => !ic || ic.includes(x.s)).map(x => x.s + "=" + x.v).sort().join("|");
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
    for (let tur = 0; tur < 4; tur++) {
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
      top += deg; if (!deg) break; await bekle(220);
    }
    return top;
  }

  // ---- alan (blok) bulma
  const BLOK = ".card,.kc,.tkp,.yan,.box,.panel,aside,article,.chartbox,.kpi,.tile,figure,table,.tw";
  const UIDISI = "#alcoTop,.ss-ui,html,body,main,header,nav,.wrap,#app,iframe";
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
  function konum(el) {
    const tag = el.tagName.toLowerCase(), cls = sinif(el), n = norm(baslik(el));
    const ayni = $$(tag + (cls ? "." + CSS.escape(cls) : "")).filter(x => norm(baslik(x)) === n);
    return { id: el.id || "", tag, cls, n, i: Math.max(0, ayni.indexOf(el)), yol: cssYol(el) };
  }
  function bul(L) {
    if (!L) return null;
    if (L.id) { const e = document.getElementById(L.id); if (e) return e; }
    const ayni = $$(L.tag + (L.cls ? "." + CSS.escape(L.cls) : "")).filter(x => norm(baslik(x)) === L.n && !x.closest(".ss-ui"));
    if (ayni.length) return ayni[Math.min(L.i, ayni.length - 1)];
    try { const e = document.querySelector(L.yol); if (e) return e; } catch (e) {}
    return null;
  }
  function ogeYap(el) {
    const r = el.getBoundingClientRect();
    const ic = [...new Set([...$$(DUGME, el).map(b => grupOf(b)?.id), ...$$("select[id]", el).map(x => x.id)].filter(Boolean))];
    const kk = /^Kaynak:/.test(el.getAttribute("title") || "") ? el.getAttribute("title").replace(/^Kaynak:\s*/, "") : "";
    return { id: uid(), sayfa: SAYFA, ad: baslik(el) || "Alan", yolAd: yolAd(), konum: konum(el), durum: durumAl(), ic, kk, w: Math.round(r.width), h: Math.round(r.height), t: Date.now() };
  }
  const buDurumda = (o, st) => imza(o.durum, o.ic) === imza(st || durumAl(), o.ic);
  function ekliMi(el, st) {
    const L = konum(el);
    return ogeler(oku()).find(o => o.sayfa === SAYFA && o.konum.tag === L.tag && o.konum.cls === L.cls && o.konum.n === L.n && o.konum.i === L.i && buDurumda(o, st));
  }

  // ---- seçim modu
  const modAcik = () => ls.get(KM) === "1";
  const CSS_UI = `
.ss-ui{font-family:"DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
.ss-hl{position:fixed;pointer-events:none;z-index:2147483000;border:2px solid #c8102e;border-radius:12px;background:rgba(200,16,46,.05);box-shadow:0 0 0 4px rgba(200,16,46,.12);transition:all .08s ease-out;display:none}
.ss-hl.ekli{border-style:solid;background:rgba(11,122,11,.05);border-color:#0b7a0b;box-shadow:0 0 0 4px rgba(11,122,11,.12)}
.ss-et{position:fixed;z-index:2147483001;display:none;align-items:stretch;gap:0;background:#c8102e;color:#fff;border-radius:9px;box-shadow:0 6px 18px rgba(0,0,0,.22);font-size:12.5px;font-weight:700;overflow:hidden;white-space:nowrap}
.ss-et.ekli{background:#0b7a0b}
.ss-et button{all:unset;cursor:pointer;padding:6px 10px;display:inline-flex;align-items:center;gap:5px;font:inherit}
.ss-et button:hover{background:rgba(255,255,255,.16)}
.ss-et button+button{border-left:1px solid rgba(255,255,255,.28)}
.ss-et .ad{font-weight:500;opacity:.85;max-width:220px;overflow:hidden;text-overflow:ellipsis}
.ss-rozet{position:absolute;z-index:2147482999;pointer-events:none;background:#0b7a0b;color:#fff;font:700 11px/1 "DM Sans",system-ui,sans-serif;border-radius:0 10px 0 8px;padding:5px 8px}
.ss-cerceve{position:absolute;z-index:2147482998;pointer-events:none;border:2px dashed #0b7a0b;border-radius:12px}
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

  let hl, et, aday = [], seviye = 0, kilit = false, isaretler = [];
  function uiKur() {
    if (hl) return; stilEkle();
    hl = Object.assign(document.createElement("div"), { className: "ss-hl ss-ui" });
    et = Object.assign(document.createElement("div"), { className: "ss-et ss-ui" });
    document.body.append(hl, et);
    et.addEventListener("mouseenter", () => { kilit = true; });
    et.addEventListener("mouseleave", () => { kilit = false; });
    et.addEventListener("click", e => {
      e.preventDefault(); e.stopPropagation();
      const b = e.target.closest("button"); if (!b) return; const el = aday[seviye]; if (!el) return;
      if (b.dataset.a === "buyut") { seviye = Math.min(aday.length - 1, seviye + 1); ciz(); return; }
      if (b.dataset.a === "kucult") { seviye = Math.max(0, seviye - 1); ciz(); return; }
      const var_ = ekliMi(el);
      if (var_) { cikar(var_.id); toast("Sunumdan çıkarıldı"); }
      else { const d = ekle(ogeYap(el)); toast(`Eklendi · ${d.slaytlar.length}. slayt`); }
      ciz(); isaretle();
    });
  }
  function ciz() {
    const el = aday[seviye]; if (!el || !el.isConnected) { hl.style.display = et.style.display = "none"; return; }
    const r = el.getBoundingClientRect(), ek = !!ekliMi(el);
    Object.assign(hl.style, { display: "block", left: r.left - 3 + "px", top: r.top - 3 + "px", width: r.width + 6 + "px", height: r.height + 6 + "px" });
    hl.classList.toggle("ekli", ek); et.classList.toggle("ekli", ek);
    et.innerHTML = `<button data-a="ekle">${ek ? "✓ Sunumda · çıkar" : "＋ Sunuma ekle"} <span class="ad">${esc(baslik(el))}</span></button>` +
      (seviye < aday.length - 1 ? `<button data-a="buyut" title="Daha geniş alanı seç">⤢</button>` : "") + (seviye > 0 ? `<button data-a="kucult" title="Daha dar alanı seç">⤡</button>` : "");
    et.style.display = "flex";
    const ew = et.offsetWidth, eh = et.offsetHeight;
    let x = Math.min(innerWidth - ew - 6, Math.max(6, r.right - ew - 8)), y = r.top + 8;
    if (y < 4) y = 4; if (y > innerHeight - eh - 4) y = Math.max(4, Math.min(innerHeight - eh - 4, r.bottom - eh - 8));
    et.style.left = x + "px"; et.style.top = y + "px";
  }
  function hareket(e) {
    if (!modAcik() || kilit || PAGE === "sunum") return;
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
      if (o.sayfa !== SAYFA || !buDurumda(o, st)) return;
      const el = bul(o.konum); if (!el || !el.offsetParent) return;
      const r = el.getBoundingClientRect(), sx = scrollX, sy = scrollY;
      const c = Object.assign(document.createElement("div"), { className: "ss-cerceve ss-ui" });
      Object.assign(c.style, { left: r.left + sx - 3 + "px", top: r.top + sy - 3 + "px", width: r.width + 6 + "px", height: r.height + 6 + "px" });
      const z = Object.assign(document.createElement("div"), { className: "ss-rozet ss-ui", textContent: `✓ Slayt ${si + 1}` });
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

  // alt çubuk (en üst pencerede)
  let bar;
  function barCiz() {
    if (!UST || IZOLE || PAGE === "sunum") return;
    if (!modAcik()) { if (bar) bar.remove(); bar = null; return; }
    stilEkle();
    if (!bar) { bar = Object.assign(document.createElement("div"), { className: "ss-bar ss-ui" }); document.body.appendChild(bar);
      bar.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return;
        if (b.dataset.a === "bitti") api.bitir(); else if (b.dataset.a === "ac") api.ac(); else if (b.dataset.a === "geri") { const d = oku(), o = ogeler(d).sort((a, b) => b.t - a.t)[0]; if (o) { cikar(o.id); toast("Son eklenen çıkarıldı"); } } }); }
    const d = oku(), n = ogeler(d).length;
    bar.innerHTML = `<span class="nokta"></span><span class="ip"><b style="color:#fff">Seçim modu</b> · Alanın üzerine gelip <b style="color:#fff">＋ Sunuma ekle</b>'ye tıklayın. Grafiği istediğiniz görünüme getirip ekleyebilir, sekmeler arasında gezebilirsiniz.</span>
      <span class="say">${n} alan · ${d.slaytlar.length} slayt</span><button data-a="geri" ${n ? "" : "disabled"} title="Son ekleneni çıkar">↶</button><button class="ana" data-a="ac">Sunumu hazırla →</button><button data-a="bitti">Bitti</button>`;
  }

  function modDegisti() {
    document.documentElement.classList.toggle("ss-mod", modAcik() && !IZOLE && PAGE !== "sunum");
    if (modAcik() && !IZOLE && PAGE !== "sunum") uiKur(); else if (hl) { hl.style.display = et.style.display = "none"; aday = []; }
    barCiz(); isaretle(); dugmeGuncelle();
  }

  // ---- üst başlıktaki "Sunum" düğmesi ve menü
  function dugmeGuncelle() {
    const b = document.getElementById("atSunum"); if (!b) return;
    const n = ogeler(oku()).length;
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
      ${n ? `<hr><button data-a="yeni"><i>⟲</i>Yeni sunum<small>Seçili ${n} alanı temizle</small></button>` : ""}`;
    document.body.appendChild(p);
    const r = cap.getBoundingClientRect();
    p.style.top = r.bottom + scrollY + 6 + "px";
    p.style.left = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, r.right + scrollX - p.offsetWidth)) + "px";
    p.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; e.stopPropagation(); p.remove();
      if (b.dataset.a === "mod") modAcik() ? api.bitir() : api.basla();
      if (b.dataset.a === "ac") api.ac();
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
  let hedef = null, izOge = null;
  async function izole(o) {
    izOge = o;
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
    const t0 = Date.now(); let onceki = "", sabit = 0, el = null;
    while (Date.now() - t0 < 30000) {
      const deg = await durumUygula(o.durum);
      el = bul(o.konum);
      const r = el && el.getBoundingClientRect(), olcu = r ? Math.round(r.width) + "x" + Math.round(r.height) : "";
      if (el && r.height > 20 && !deg && olcu === onceki) { if (++sabit >= 2) break; } else sabit = 0;
      onceki = olcu; await bekle(350);
    }
    if (!el) { document.body.innerHTML = `<div style="font:14px system-ui;color:#888;padding:30px;text-align:center">Bu alan sayfada bulunamadı: <b>${esc(o.ad)}</b><br>Sayfa yapısı değişmiş olabilir; slaytı silip alanı yeniden ekleyin.</div>`; root.classList.remove("ss-izole"); haber({ hata: 1, w: 500, h: 120 }); return; }
    yerlestir(el);
    new MutationObserver(() => { if (!hedef || !hedef.isConnected) { const y = bul(o.konum); if (y) yerlestir(y); } }).observe(document.body, { childList: true, subtree: true });
  }
  let ro;
  function yerlestir(el) {
    $$("[data-ss-gizle]").forEach(x => x.removeAttribute("data-ss-gizle")); $$("[data-ss-yol]").forEach(x => x.removeAttribute("data-ss-yol"));
    if (hedef) hedef.removeAttribute("data-ss-hedef");
    hedef = el; el.setAttribute("data-ss-hedef", "");
    if (izOge && izOge.w) el.style.setProperty("width", Math.max(200, izOge.w) + "px", "important");
    for (let x = el; x && x !== document.body; x = x.parentElement) {
      if (x !== el) x.setAttribute("data-ss-yol", "");
      for (const s of x.parentElement ? x.parentElement.children : []) if (s !== x && !/^(SCRIPT|STYLE|LINK)$/.test(s.tagName) && !s.classList.contains("tip") && !s.classList.contains("tt")) s.setAttribute("data-ss-gizle", "");
    }
    dispatchEvent(new Event("resize"));
    if (ro) ro.disconnect();
    ro = new ResizeObserver(() => haber()); ro.observe(el);
    setTimeout(haber, 50);
  }
  let sonOlcu = "";
  function haber(x) {
    const r = hedef ? hedef.getBoundingClientRect() : null;
    const m = x || { w: Math.ceil(r ? Math.max(r.width, hedef.scrollWidth) : 0), h: Math.ceil(r ? Math.max(r.height, hedef.scrollHeight) : 0) };
    const k = m.w + "x" + m.h + (m.hata ? "!" : ""); if (k === sonOlcu) return; sonOlcu = k;
    try { parent.postMessage({ ssBoyut: 1, id: Q.get("sunum"), ...m }, location.origin); } catch (e) {}
  }

  // yakalama: dışa aktarma için alanın PNG görüntüsü
  const libYukle = (ad, glob) => window[glob] ? Promise.resolve(window[glob]) : new Promise((ok, no) => {
    const s = document.createElement("script"); s.src = new URL("ortak/lib/" + ad, KOK).href; s.onload = () => ok(window[glob]); s.onerror = () => no(new Error(ad + " yüklenemedi")); document.head.appendChild(s); });
  async function yakala(pr = 2) {
    if (!hedef) throw new Error("alan yok");
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
    menu, modAcik, _yenile: modDegisti, _yolAd: () => yolAd(),
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
    document.addEventListener("mousemove", hareket, { passive: true });
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
