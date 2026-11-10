// Ortak üst başlık: DOST KATILIM - PİYASA VERİLERİ (ALCO)
// Kullanım: <div id="alcoTop"></div><script src="<kök>/ortak/ust.js" data-page="banka|katilim|tefas|makro|tcmb" data-root="<kök>/"></script>
// Kök index.html (kabuk.html) data-shell="1" ile çağırır: sekmeler iframe olarak açılır, sayfa yeniden yüklenmez.
// Kabuk içinde açılan sayfalarda başlık çizilmez; tema kabuktan window.alcoTema ile gelir.
// Tarih, PPK geri sayımı, koyu/açık tema ve veri güncelliği (durum.json) gösterir.
(function () {
  const me = document.currentScript, PAGE = me.dataset.page || "", ROOT = me.dataset.root || "./";
  const host = document.getElementById("alcoTop"); if (!host) return;
  const SHELL = me.dataset.shell === "1";
  let EMBED = false, IC = false;     // IC: kabuktaki bir sayfanın içine gömülü (ör. Bankacılık → TCMB Rezervler)
  try { EMBED = !SHELL && window.parent !== window && !!window.parent.document; IC = EMBED && !window.parent.document.getElementById("alcoFrames"); } catch (e) {}
  if (IC) document.documentElement.classList.add("alco-ic");
  const AY = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
  const get = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const set = (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} };
  const root = document.documentElement;
  const saved = get("alco-theme") || get("fd-theme") || get("bv.theme"); if (saved) root.dataset.theme = saved;
  const isDark = () => root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  // sayfanın temasını t'ye getir (TEFAS kendi düğmesiyle grafikleri de yeniden çizer)
  const temaUygula = t => {
    if ((t === "dark") !== isDark()) { const thm = document.getElementById("thm"); if (PAGE === "tefas" && thm) thm.click(); }
    root.dataset.theme = t; window.dispatchEvent(new Event("resize"));
  };
  window.alcoTema = t => { temaUygula(t); set("alco-theme", t); set("fd-theme", t); set("bv.theme", t);
    if (!SHELL) document.querySelectorAll("iframe").forEach(f => { try { f.contentWindow.alcoTema && f.contentWindow.alcoTema(t); } catch (e) {} }); };

  // PDF: sayfayı açık temada, başlıklı ve A4 yatay olarak yazdır ("PDF olarak kaydet")
  const AD = { ozet: "Özet", bilanco: "Banka Bilanço Verileri", banka: "Bankacılık Verileri", katilim: "Katılım Bülteni", tefas: "TEFAS Verileri", makro: "Makro ve Piyasa Verileri", tcmb: "TCMB" };
  const AYU = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
  document.head.appendChild(Object.assign(document.createElement("style"), { textContent: `
#alcoPrintHead{display:none}
@page{size:A3 landscape;margin:9mm}
@media print{
  html,body{-webkit-print-color-adjust:exact;print-color-adjust:exact;background:#fff!important}
  #alcoTop,header.alco-top,#atPdf,.at-noprint{display:none!important}
  details:not([open]){display:none!important}
  #alcoPrintHead{display:flex!important;justify-content:space-between;align-items:flex-end;border-bottom:2px solid #c8102e;padding:0 0 6px;margin:0 0 10px;font-family:"DM Sans",system-ui,sans-serif;color:#1c1416}
  #alcoPrintHead b{font-size:15px;font-weight:800}#alcoPrintHead b span{color:#c8102e}#alcoPrintHead small{display:block;font-size:11px;color:#7a6a6c}
  #alcoPrintHead em{font-style:normal;font-size:12px;color:#7a6a6c;text-align:right}
  .card,article,.box{break-inside:avoid}
}` }));
  window.alcoPdf = () => {
    const now = new Date(), ad = AD[PAGE] || "Piyasa Verileri";
    let h = document.getElementById("alcoPrintHead");
    if (!h) { h = document.createElement("div"); h.id = "alcoPrintHead"; document.body.insertBefore(h, document.body.firstChild); }
    h.innerHTML = `<div><b><span>DOST KATILIM</span> - PİYASA VERİLERİ (ALCO)</b><small>${ad}</small></div><em>${now.getDate()} ${AYU[now.getMonth()]} ${now.getFullYear()}<br>Veri Takip Dashboard</em>`;
    const eskiT = document.title, eskiTema = root.dataset.theme, koyu = isDark();
    document.title = `ALCO - ${ad} - ${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    if (koyu) temaUygula("light");
    const bitti = () => {
      document.title = eskiT;
      if (koyu) { if (eskiTema) temaUygula(eskiTema); else { temaUygula("dark"); delete root.dataset.theme; } }
      window.removeEventListener("afterprint", bitti);
    };
    window.addEventListener("afterprint", bitti);
    setTimeout(() => window.print(), koyu || PAGE === "tefas" ? 1500 : 300);   // grafikler yeniden çizilsin
  };
  // Sunum oluşturucu (seçim modu, izole slayt gösterimi): her sayfada yüklenir
  if (!document.getElementById("ssJs")) { const s = document.createElement("script"); s.id = "ssJs"; s.src = ROOT + "ortak/sunum.js?v=" + Math.floor(Date.now() / 36e5); s.dataset.root = ROOT; s.dataset.page = PAGE; document.head.appendChild(s); }
  if (EMBED) {
    host.remove();
    document.head.appendChild(Object.assign(document.createElement("style"), { textContent: "#thm{display:none!important}" }));
    return;
  }

  const css = `
.alco-top{--at-bg:#fff;--at-ink:#1c1416;--at-mut:#7a6a6c;--at-line:#eadfe0;--at-red:#c8102e;--at-dark:#8b0f1a;--at-wash:#fdecee;--at-ok:#1f8a4c;--at-warn:#c77700;
  background:var(--at-bg);border-bottom:1px solid var(--at-line);font-family:"DM Sans","Albert Sans",system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--at-ink);position:relative;z-index:20}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .alco-top{--at-bg:#171012;--at-ink:#f3e9ea;--at-mut:#b49ea1;--at-line:#3a2a2d;--at-red:#f0525f;--at-dark:#ff8a94;--at-wash:#3a171b;--at-ok:#4cc27a;--at-warn:#f0a84a}}
:root[data-theme="dark"] .alco-top{--at-bg:#171012;--at-ink:#f3e9ea;--at-mut:#b49ea1;--at-line:#3a2a2d;--at-red:#f0525f;--at-dark:#ff8a94;--at-wash:#3a171b;--at-ok:#4cc27a;--at-warn:#f0a84a}
.alco-top{display:block!important;padding:0!important;justify-content:initial;align-items:initial;text-align:left}
.alco-top nav.at-tabs{background:none!important;border-radius:0!important;padding:0!important;flex-wrap:nowrap!important;align-items:stretch!important}
.alco-top nav.at-tabs a{opacity:1!important;border-radius:0!important}
.alco-top h1,.alco-top small{font-family:inherit}
.alco-top .at-in{max-width:1500px;margin:0 auto;padding:12px max(16px,env(safe-area-inset-left,0px)) 0 max(16px,env(safe-area-inset-left,0px))}
.alco-top .at-r1{display:flex;flex-wrap:wrap;align-items:center;gap:10px 18px;padding-bottom:10px}
.alco-top .at-brand{margin-right:auto;min-width:0}
.alco-top .at-brand b{display:block;font-size:20px;font-weight:800;letter-spacing:.01em;line-height:1.2}
.alco-top .at-brand b span{color:var(--at-red)}
.alco-top .at-brand small{display:block;font-size:12.5px;color:var(--at-mut);margin-top:1px}
.alco-top .at-date{border:1px solid var(--at-line);background:var(--at-wash);border-radius:10px;padding:6px 14px;text-align:center;line-height:1.25}
.alco-top .at-date b{display:block;font-family:"JetBrains Mono","Spline Sans Mono",ui-monospace,monospace;font-size:15px;color:var(--at-red);font-weight:700}
.alco-top .at-date small{font-size:11.5px;color:var(--at-mut)} .alco-top .at-date small i{font-style:normal;color:var(--at-red);font-weight:600}
.alco-top button.at-btn{font:inherit;font-size:13px;font-weight:600;border:1px solid var(--at-line);background:var(--at-bg);color:var(--at-ink);border-radius:9px;padding:7px 12px;cursor:pointer}
.alco-top button.at-btn:hover{border-color:var(--at-red)}
.alco-top .at-fr{position:relative}
.alco-top .at-fr .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--at-ok);margin-right:6px;vertical-align:1px}
.alco-top .at-fr.warn .dot{background:var(--at-warn)}
.alco-top .at-fr b{color:var(--at-red)}
.alco-top .at-pop{position:absolute;right:0;top:calc(100% + 6px);background:var(--at-bg);border:1px solid var(--at-line);border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.15);padding:8px 10px;min-width:340px;z-index:30;font-size:12.5px}
.alco-top .at-pop div{display:grid;grid-template-columns:12px minmax(0,1fr) auto;gap:8px;padding:5px 2px;border-bottom:1px solid var(--at-line);align-items:center}
.alco-top .at-pop div:last-child{border-bottom:0}
.alco-top .at-pop i{width:8px;height:8px;border-radius:50%;background:var(--at-ok)} .alco-top .at-pop i.w{background:var(--at-warn)} .alco-top .at-pop i.n{background:var(--at-line)}
.alco-top .at-pop span:last-child{font-family:"JetBrains Mono",ui-monospace,monospace;color:var(--at-mut);font-size:11.5px}
.alco-top nav.at-tabs{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none}.alco-top nav.at-tabs::-webkit-scrollbar{display:none}
.alco-top nav.at-tabs a{display:inline-flex;align-items:center;gap:6px;text-decoration:none;color:var(--at-mut);font-size:14px;font-weight:600;padding:10px 16px 11px;border-bottom:3px solid transparent;white-space:nowrap}
.alco-top nav.at-tabs a:hover{color:var(--at-ink);background:none}
.alco-top nav.at-tabs a[aria-current="page"]{color:var(--at-red);border-bottom-color:var(--at-red)}
.alco-top nav.at-tabs a .b{font-size:10.5px;min-width:18px;height:18px;border-radius:9px;background:var(--at-ok);color:#fff;display:inline-flex;align-items:center;justify-content:center;padding:0 5px}
.alco-top nav.at-tabs a .b.w{background:var(--at-warn)}
.alco-top nav.at-tabs a .b[hidden]{display:none}
@media (max-width:640px){.alco-top .at-brand b{font-size:16px}.alco-top .at-date{padding:4px 10px}}
${PAGE === "tefas" ? "#thm{display:none!important}" : ""}`;
  document.head.appendChild(Object.assign(document.createElement("style"), { textContent: css }));

  const TABS = [["ozet", "Özet", "ozet/", "ozet/"], ["banka", "Bankacılık Verileri", "bankacilik/", "bankacilik/"], ["tefas", "TEFAS Verileri", "", "tefas.html"], ["makro", "Makro ve Piyasa", "makro/", "makro/"], ["bilanco", "Banka Bilanço Verileri", "bilanco/", "bilanco/"]];
  const ALIAS = { katilim: ["banka", "katilim"], tcmb: ["banka", "rezerv"], rezerv: ["banka", "rezerv"], zk: ["banka", "zk"], pp: ["banka", "pp"], bddk: ["banka", "bddk"],   // eski bağlantılar ve Özet kartları: alt sekmeler
    enf: ["makro", "enf"], piyasa: ["makro", "piyasa"], buyume: ["makro", "buyume"], istihdam: ["makro", "istihdam"], uretim: ["makro", "uretim"], dis: ["makro", "dis"], butce: ["makro", "butce"], hazine: ["makro", "hazine"] };
  const SRC = [ // anahtar, ad, sekme, kaç gün içinde "güncel"
    ["bddk_haftalik", "BDDK Haftalık Bülten", "banka", 14], ["bddk_aylik", "BDDK Aylık Bülten", "banka", 75],
    ["evds", "TCMB EVDS", "banka", 7], ["politika", "Para Politikası (TCMB)", "banka", 5],
    ["katilim", "Katılım Bülteni", "banka", 10], ["tefas", "TEFAS", "tefas", 4],
    ["tufe", "Enflasyon (TÜİK)", "makro", 40], ["piyasa", "Piyasa (TLREF, repo)", "makro", 5],
    ["rezerv", "TCMB Rezervler (EVDS)", "banka", 5], ["zk", "Zorunlu karşılık (TCMB)", "banka", 5], ["hazine", "Hazine Borçlanma (HMB)", "makro", 45], ["ekonomi", "Ekonomik göstergeler (TÜİK, EVDS)", "makro", 45], ["ozet", "Özet ve haber akışı (ForInvest)", "ozet", 2], ["bilanco", "Banka bilanço (KAP finansal raporlar)", "bilanco", 110]];
  const now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const fmt = d => `${d.getDate()} ${AY[d.getMonth()]} ${d.getFullYear()}`;
  const parse = s => { if (!s) return null; if (/^\d{4}-\d{2}$/.test(s)) { const [y, m] = s.split("-").map(Number); return new Date(y, m, 0); } const [y, m, d] = s.slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); };

  host.innerHTML = `<header class="alco-top"><div class="at-in"><div class="at-r1">
    <div class="at-brand"><b><span>DOST KATILIM</span> - PİYASA VERİLERİ (ALCO)</b><small>Veri Takip Dashboard</small></div>
    <div class="at-date"><b>${fmt(now)}</b><small id="atPpk">&nbsp;</small></div>
    <button type="button" class="at-btn" id="atPdf" title="Bu sayfayı PDF olarak kaydet (yazdır → PDF olarak kaydet)">⤓ PDF</button>
    <button type="button" class="at-btn" id="atTheme"></button>
    <div class="at-fr" id="atFr"><button type="button" class="at-btn" id="atFrBtn" aria-expanded="false"><span class="dot"></span>Veri durumu</button></div>
  </div><nav class="at-tabs" aria-label="Bölümler">${TABS.map(([k, n, p]) => `<a href="${SHELL ? "#" + k : ROOT + "#" + k}" data-k="${k}"${k === (ALIAS[PAGE] ? ALIAS[PAGE][0] : PAGE) ? ' aria-current="page"' : ""}>${n}<span class="b" hidden></span></a>`).join("")}</nav></div></header>`;

  const tb = document.getElementById("atTheme");
  const lab = () => { tb.textContent = isDark() ? "☀ Açık" : "☾ Koyu"; };
  lab();
  tb.onclick = () => {
    const t = isDark() ? "light" : "dark";
    window.alcoTema(t); lab();
    if (SHELL) document.querySelectorAll("#alcoFrames iframe").forEach(f => { try { f.contentWindow.alcoTema && f.contentWindow.alcoTema(t); } catch (e) {} });
  };

  document.getElementById("atPdf").onclick = () => {
    if (SHELL) { const f = [...document.querySelectorAll("#alcoFrames iframe")].find(x => !x.hidden); try { if (f && f.contentWindow.alcoPdf) return f.contentWindow.alcoPdf(); } catch (e) {} if (f) { try { f.contentWindow.print(); return; } catch (e) {} } }
    window.alcoPdf();
  };

  if (SHELL) { // tek sayfa: sekmeler iframe; bir kez açılan sekme bellekte kalır, geçiş anında olur
    const box = document.getElementById("alcoFrames"), frames = {};
    const show = k => {
      let ic = null; if (ALIAS[k]) [k, ic] = ALIAS[k]; else if (/^piyasa-/.test(k)) [k, ic] = ["makro", k];   // Özet kartları: piyasa-<alt sekme>[-<kalem>]
      if (!TABS.some(t => t[0] === k)) k = TABS[0][0];
      if (ic && frames[k]) { try { const w = frames[k].contentWindow; if (w.location.hash === "#" + ic) w.dispatchEvent(new HashChangeEvent("hashchange")); else w.location.hash = ic; } catch (e) {} }
      host.querySelectorAll("nav.at-tabs a").forEach(a => { if (a.dataset.k === k) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
      for (const [kk, f] of Object.entries(frames)) f.hidden = kk !== k;
      if (!frames[k]) {
        const t = TABS.find(x => x[0] === k), f = document.createElement("iframe");
        f.title = t[1]; f.src = t[3] + "?v=" + Math.floor(Date.now() / 6e4) + (ic ? "#" + ic : "");   // ?v: tarayıcı önbelleğindeki eski sayfa yerine güncelini aç
        box.appendChild(f); frames[k] = f;
      } else { try { frames[k].contentWindow.dispatchEvent(new Event("resize")); } catch (e) {} }
      document.title = TABS.find(x => x[0] === k)[1] + " · ALCO";
    };
    host.querySelector("nav.at-tabs").addEventListener("click", e => {
      const a = e.target.closest("a[data-k]"); if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
      e.preventDefault(); if (location.hash !== "#" + a.dataset.k) history.pushState(null, "", "#" + a.dataset.k); show(a.dataset.k);
    });
    addEventListener("popstate", () => show(location.hash.slice(1)));
    show(location.hash.slice(1));
  }

  fetch(ROOT + "durum.json?t=" + Date.now(), { cache: "no-store" }).then(r => r.ok ? r.json() : {}).catch(() => ({})).then(D => {
    D = D || {};
    if (D.ppk_sonraki) { const p = parse(D.ppk_sonraki), g = Math.round((p - today) / 864e5); if (g >= 0) document.getElementById("atPpk").innerHTML = `PPK: ${p.getDate()} ${AY[p.getMonth()]} · <i>${g === 0 ? "bugün" : g + "g"}</i>`; }
    const rows = SRC.map(([k, n, tab, lim]) => { const e = D[k], d = e && parse(e.son_veri), age = d ? Math.round((today - d) / 864e5) : null; return { k, n, tab, d, ok: d != null && age <= lim, has: !!d }; });
    const okN = rows.filter(r => r.ok).length, hasN = rows.filter(r => r.has).length;
    const fr = document.getElementById("atFr"), btn = document.getElementById("atFrBtn");
    if (!hasN) { btn.innerHTML = '<span class="dot"></span>Veri durumu'; }
    else { btn.innerHTML = `<span class="dot"></span><b>${okN}</b> güncel · ${rows.length} kaynak`; if (okN < rows.length) fr.classList.add("warn"); }
    btn.onclick = e => {
      e.stopPropagation(); const open = fr.querySelector(".at-pop"); if (open) { open.remove(); btn.setAttribute("aria-expanded", "false"); return; }
      const p = document.createElement("div"); p.className = "at-pop";
      p.innerHTML = rows.map(r => `<div><i class="${r.has ? (r.ok ? "" : "w") : "n"}"></i><span>${r.n}</span><span>${r.d ? "son veri " + fmt(r.d) : "bilgi yok"}</span></div>`).join("");
      fr.appendChild(p); btn.setAttribute("aria-expanded", "true");
    };
    document.addEventListener("click", () => { const o = fr.querySelector(".at-pop"); if (o) { o.remove(); btn.setAttribute("aria-expanded", "false"); } });
    for (const [k] of TABS) {
      const rs = rows.filter(r => r.tab === k && r.has); if (!rs.length) continue;
      const b = host.querySelector(`a[data-k="${k}"] .b`), n = rs.filter(r => r.ok).length;
      b.textContent = n < rs.length ? "!" : "✓"; b.title = `${n}/${rs.length} kaynak güncel`; if (n < rs.length) b.classList.add("w"); b.hidden = false;
    }
  });
})();
