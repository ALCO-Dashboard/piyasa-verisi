// ================================================================ BIST Bülten Verileri (BAP ve KMTP)
// Veri: data/bist.json (günlük özetler, bist/guncelle.py), data/bist/YYYY-MM-DD.json (işlem detayları), data/bist_kiymet.json (ihraççı)
// makro/sayfa.html içine derleme sırasında gömülür; sayfanın yardımcılarını (chart, tarihChips, veriIS, nf …) kullanır.
let BI;                 // bist.json (undefined: yüklenmedi, null: yok)
let BIK;                // bist_kiymet.json
const BIDET = {};       // gün → detay
const BS = { b: "bap", m: "kes", seg: new Set(["hdibs", "hsukuk", "osukuk", "ozel"]), kT: "sabit", kTen: new Set(["1", "3", "4", "5"]),
  r: {}, det: {}, detOn: {} };
const BI_SEG = [["hdibs", "Hazine DİBS", "--c1"], ["hsukuk", "Hazine kira sertifikası", "--c3"], ["osukuk", "Özel sektör kira sertifikası", "--c6"], ["ozel", "Özel sektör bono / tahvil", "--c4"]];
const BI_TUR = [["sabit", "Sabit getirili", "--c1"], ["tufe", "TÜFE'ye endeksli", "--c2"], ["tlref", "TLREF / TLREFK'ya endeksli", "--c3"], ["degisken", "Değişken faizli", "--c6"]];
const BI_TEN = ["1A", "3A", "6A", "1Y", "2Y", "5Y", "10Y"];
const BI_TEN_COL = ["--c5", "--c6", "--c4", "--c1", "--c3", "--c2", "--ink-2"];
const BI_PZ = [["kes", "KES Alım Satım"], ["repo", "Repo-Ters Repo"], ["ctm", "Taahhütlü İşlem (Kira Sertifikası)"], ["fxsw", "Para Swap"], ["mktr", "MK Tercihli Repo"],
  ["prep", "Pay Repo"], ["para", "Para Piyasası"], ["kmsw", "Kıymetli Maden Swap"], ["brep", "Bankalararası Repo"], ["ihrac", "Nitelikli Yatırımcı İhraç"]];
const BI_PZ_AD = { kes: "KES", repo: "Repo-T.Repo (normal)", repos: "Repo-T.Repo (küçük emir)", brep: "Bankalararası repo", ctm: "Taahhütlü işlem", fxsw: "Para swap",
  mktr: "MK tercihli repo", prep: "Pay repo", para: "Para piyasası", kmsw: "KM swap", ihrac: "İhraç pazarı", eurob: "Eurobond", diger: "Diğer" };
const BI_MET = [["au", "Altın", "--c4"], ["ag", "Gümüş", "--c6"], ["pt", "Platin", "--c3"], ["pd", "Paladyum", "--c2"]];

const biMr = (v, d = 1) => !ok(v) ? "—" : Math.abs(v) < 1e3 && v ? `${nf(v, v < 10 ? 1 : 0)} mn ₺` : `${nf(v / 1e3, v >= 1e5 ? 0 : d)} mr ₺`;     // milyon TL → milyar (1 milyarın altı milyon)
const biPc = v => ok(v) ? `${v > 0 ? "+" : v < 0 ? "−" : ""}%${nf(Math.abs(v), 1)}` : "—";
const biCh = (a, b) => ok(a) && ok(b) && b ? (a / b - 1) * 100 : null;
const biDates = () => Object.keys(BI?.g || {}).sort();
const biKmDates = () => Object.keys(BI?.km || {}).filter(d => BI.km[d]?.au || BI.km[d]?.ag).sort();
// son 5 iş günü toplamı ve önceki 5 günle değişim
function biHafta(vals, i) { const s = (a, b) => { let t = 0, n = 0; for (let k = a; k <= b; k++) if (k >= 0 && ok(vals[k])) { t += vals[k]; n++; } return n ? t : null; };
  const a = s(i - 4, i), b = s(i - 9, i - 5); return { top: a, onc: b, deg: biCh(a, b) }; }
const biOnce = (dates, i, gun) => { const h = new Date(Date.parse(dates[i]) - gun * 864e5).toISOString().slice(0, 10); for (let k = i; k >= 0; k--) if (dates[k] <= h) return k; return -1; };

// ---- KES hücre toplamları: c = [seg, tur, ten, hacim, yw, yh, pw, ph]
function biKes(g, segs, tur, ten) {
  let h = 0, yw = 0, yh = 0, pw = 0, ph = 0;
  for (const c of g?.k || []) { if (!segs.has(c[0])) continue; if (tur && c[1] !== tur) continue; if (ten != null && c[2] !== +ten) continue;
    h += c[3]; yw += c[4]; yh += c[5]; pw += c[6] || 0; ph += c[7] || 0; }
  return { h, y: yh ? yw / yh : null, p: ph ? pw / ph : null, yh };
}
// getiri yoksa (endeksli / kira sertifikası) ağırlıklı ortalama fiyat
const biDeger = x => ok(x.y) ? { v: x.y, f: v => pct(v, 2), ch: bp, tip: "getiri" } : ok(x.p) ? { v: x.p, f: v => nf(v, 3), ch: v => (v > 0 ? "+" : v < 0 ? "−" : "") + nf(Math.abs(v), 3), tip: "fiyat" } : null;

// ---- OIS (SOFR / €STR) vade enterpolasyonu: Bloomberg USD OIS / EUR OIS sayfaları
const OIS_GUN = { ON: 1, "1W": 7, "2W": 14, "1M": 30, "2M": 61, "3M": 91, "6M": 182, "9M": 273, "1Y": 365, "18M": 547, "2Y": 730, "3Y": 1095, "5Y": 1825, "10Y": 3650 };
function biOis(ccy, tarih, gun) {
  const t = B?.tablolar?.[ccy === "USD" ? "USD OIS" : "EUR OIS"]; if (!t) return null;
  let i = t.dates.length - 1; while (i > 0 && t.dates[i] > tarih) i--;
  const p = t.kolonlar.map((k, j) => [OIS_GUN[k.etiket], j]).filter(x => x[0]).sort((a, b) => a[0] - b[0]);
  const val = j => { for (let k = i; k >= Math.max(0, i - 5); k--) if (ok(t.v[j][k])) return t.v[j][k]; return null; };
  const pts = p.map(([g, j]) => [g, val(j)]).filter(x => ok(x[1])); if (!pts.length) return null;
  if (gun <= pts[0][0]) return pts[0][1]; if (gun >= pts[pts.length - 1][0]) return pts[pts.length - 1][1];
  for (let k = 1; k < pts.length; k++) if (gun <= pts[k][0]) { const [g0, v0] = pts[k - 1], [g1, v1] = pts[k]; return v0 + (v1 - v0) * (gun - g0) / (g1 - g0); }
  return null;
}
// swap puanından TL implied oran: F = S + puan/10000; r_TL = ((F/S)·(1 + r_dvz·g/360) − 1)·365/g
function biImplied(cift, tarih, gun, puan, spot) {
  if (!ok(puan) || !ok(spot) || !spot || !gun) return null;
  const rf = biOis(cift.startsWith("EUR") ? "EUR" : "USD", tarih, gun); if (!ok(rf)) return null;
  const F = spot + puan / 1e4, r = ((F / spot) * (1 + rf / 100 * gun / 360) - 1) * 365 / gun * 100;
  return r > 5 && r < 150 ? r : null;        // hatalı girilmiş / uç işlemler
}
function biSwapGun(g, cift, tarih) {
  const R = g?.sw?.[cift] || []; let on = null, dh = 0, dw = 0, dwh = 0;
  // gecelik: en kısa vade (tatil öncesinde gecelik işlem birkaç gün sürebilir: ≤ 10 gün)
  const enk = R.reduce((m, x) => x[0] <= 10 && (!m || x[0] < m[0]) ? x : m, null);
  for (const x of R) { const [gun, puan, spot, h] = x, r = biImplied(cift, tarih, gun, puan, spot);
    if (x === enk) on = { gun, puan, spot, h, r }; else { dh += h; if (ok(r)) { dw += r * h; dwh += h; } } }
  return { on, dh, dr: dwh ? dw / dwh : null, n: R.length };
}

// ---- ortak parçalar
const biKpi = (t, v, s, d, kc = "--c1", ek = "", tn = "") => `<div class="kpi" style="--kc:var(${kc})"${ek}><div class="t">${t}</div><div class="v">${v}</div><div class="s">${s || ""}</div>${tn}${d ? `<div class="d">${d}</div>` : ""}</div>`;
const biKart = (id, ek = "") => `<div class="card"><div class="cardhead"><div><h3 id="${id}T"></h3><div class="sub" id="${id}S"></div></div><div class="hdr2">${ek}<span class="chips" id="${id}R"></span></div></div>
  <div class="legend" id="${id}L"></div><div class="chart" id="${id}G"></div><div class="veri" id="${id}V"></div></div>`;
const biDetKart = id => `<details class="card bidet" id="${id}" ${BS.detOn[id] ? "open" : ""}><summary><b>İşlem detayları</b><span class="sub"> · tıklayınca açılır; sütunlarda filtre, sıralama ve Excel'e aktarma</span></summary><div class="bidb"></div></details>`;
function biAralik(id, dates, yeniden, def = "3A") {
  BS.r[id] ||= def; tarihChips($("#" + id + "R"), "bi" + id, BS.r[id], dates, k => { BS.r[id] = k; yeniden(); });
  return tarihKes(dates, "bi" + id, BS.r[id]).ix;
}
const biX = ix => ix.length > 90 ? (d => `${AY[+d.slice(5, 7) - 1]} ${d.slice(2, 4)}`) : gunKisa;
function biLeg(id, ser) { $("#" + id + "L").innerHTML = ser.map(x => `<span class="chip" style="cursor:default"><i style="background:${x.color}"></i>${esc(x.name)}</span>`).join(""); }

// ---- işlem detay tablosu: sütun filtresi, sıralama, 25 satır + uzatma, Excel
// kol: [{a: başlık, f: biçim(v, satır), n: sayısal mı, x: excel değeri(v, satır)}]
const DT = {};
function dTablo(el, key, kol, satir, dosya) {
  const st = DT[key] ||= { n: 25, f: {}, s: null };
  el.innerHTML = `<div class="dtw"><table class="tbl dtb"><thead><tr>${kol.map((c, j) => `<th class="${c.n ? "" : "l"}" data-j="${j}" title="Sırala">${c.a}${st.s?.[0] === j ? (st.s[1] > 0 ? " ↑" : " ↓") : ""}</th>`).join("")}</tr>
    <tr class="flt">${kol.map((c, j) => `<th><input data-j="${j}" value="${esc(st.f[j] || "")}" placeholder="${c.n ? "&gt;0" : "ara"}" aria-label="${esc(c.a)} filtresi"></th>`).join("")}</tr></thead><tbody></tbody></table></div>
    <div class="dtf"><span class="dts"></span><span class="chips"><button class="chip" data-a="more">25 satır daha</button><button class="chip" data-a="all">Tümünü göster</button><button class="chip" data-a="clr">Filtreleri temizle</button><button class="chip" data-a="xl">Excel'e aktar</button></span></div>`;
  const uy = (v, q, num) => { q = q.trim(); if (!q) return true;
    if (num) { const m = /^([<>]=?)\s*(-?[\d.,]+)$/.exec(q), x = s => +s.replace(/\./g, "").replace(",", ".");
      if (m) { const b = x(m[2]); if (!ok(v)) return false; return m[1] === ">" ? v > b : m[1] === ">=" ? v >= b : m[1] === "<" ? v < b : v <= b; } }
    return String(v ?? "").toLocaleLowerCase("tr").includes(q.toLocaleLowerCase("tr")); };
  const govde = () => {
    let R = satir.filter(r => kol.every((c, j) => uy(c.v ? c.v(r) : r[j], st.f[j] || "", c.n)));
    if (st.s) { const [j, y] = st.s, g = r => kol[j].v ? kol[j].v(r) : r[j]; R = R.slice().sort((a, b) => { const x = g(a), z = g(b); return (x == null) - (z == null) || (x < z ? -y : x > z ? y : 0); }); }
    el.querySelector("tbody").innerHTML = R.slice(0, st.n).map(r => `<tr>${kol.map((c, j) => { const v = c.v ? c.v(r) : r[j]; return `<td class="${c.n ? "" : "l"}${c.c ? " " + c.c(v, r) : ""}">${c.f ? c.f(v, r) : esc(v ?? "—")}</td>`; }).join("")}</tr>`).join("")
      || `<tr><td class="l" colspan="${kol.length}">Kayıt yok.</td></tr>`;
    el.querySelector(".dts").textContent = `${nf(Math.min(st.n, R.length), 0)} / ${nf(R.length, 0)} satır${R.length < satir.length ? ` (toplam ${nf(satir.length, 0)})` : ""}`;
    el._R = R;
  };
  govde();
  el.querySelector("thead").onclick = e => { const th = e.target.closest("tr:first-child th[data-j]"); if (!th) return; const j = +th.dataset.j;
    st.s = st.s?.[0] === j ? (st.s[1] > 0 ? [j, -1] : null) : [j, kol[j].n ? -1 : 1]; dTablo(el, key, kol, satir, dosya); };
  el.querySelector("thead").oninput = e => { const i = e.target.closest("input[data-j]"); if (!i) return; st.f[i.dataset.j] = i.value; st.n = 25; govde(); };
  el.querySelector(".dtf").onclick = async e => { const b = e.target.closest("button[data-a]"); if (!b) return; const a = b.dataset.a;
    if (a === "more") { st.n += 25; govde(); } else if (a === "all") { st.n = 1e9; govde(); } else if (a === "clr") { st.f = {}; st.s = null; st.n = 25; dTablo(el, key, kol, satir, dosya); }
    else if (a === "xl") { b.disabled = true; try { await biXlsx(); const aoa = [kol.map(c => c.a.replace(/<[^>]+>/g, ""))].concat(el._R.map(r => kol.map((c, j) => { const v = c.v ? c.v(r) : r[j]; return c.x ? c.x(v, r) : v ?? ""; })));
      const wb = XLSX.utils.book_new(), ws = XLSX.utils.aoa_to_sheet(aoa); ws["!cols"] = kol.map(c => ({ wch: c.n ? 14 : 22 })); XLSX.utils.book_append_sheet(wb, ws, "Veri"); XLSX.writeFile(wb, dosya + ".xlsx"); }
      catch (err) { console.error(err); b.textContent = "Excel yüklenemedi"; } b.disabled = false; } };
}
let biXl;
const biXlsx = () => window.XLSX ? Promise.resolve() : (biXl ||= new Promise((ok_, no) => { const s = document.createElement("script"); s.src = "https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"; s.onload = ok_; s.onerror = no; document.head.appendChild(s); }));
// detay kartı: tarih seçimi + tablo (gün dosyası ilk açılışta yüklenir)
function biDetay(id, dates, sec, kolF, dosya) {
  const el = $("#" + id); if (!el) return;
  el.ontoggle = () => { BS.detOn[id] = el.open; if (el.open) ciz(); };
  const ciz = async () => {
    const b = el.querySelector(".bidb"), t = BS.det[id] && dates.includes(BS.det[id]) ? BS.det[id] : dates[dates.length - 1]; BS.det[id] = t;
    b.innerHTML = `<div class="ctl" style="margin:8px 0"><label class="sub">Tarih <select class="bisel">${dates.slice().reverse().map(d => `<option value="${d}"${d === t ? " selected" : ""}>${gunAd(d)}</option>`).join("")}</select></label></div><div class="bidt"><div class="empty">Yükleniyor…</div></div>`;
    b.querySelector(".bisel").onchange = e => { BS.det[id] = e.target.value; ciz(); };
    try {
      const j = BIDET[t] ||= await fetch(`data/bist/${t}.json`, { cache: "no-store" }).then(r => r.ok ? r.json() : {});
      if (!BIK) BIK = await fetch("data/bist_kiymet.json", { cache: "no-store" }).then(r => r.ok ? r.json() : {}).catch(() => ({}));
      const R = sec(j); dTablo(b.querySelector(".bidt"), id, kolF(t), R, `${dosya}-${t}`);
    } catch (e) { b.querySelector(".bidt").innerHTML = `<div class="empty">Detay yüklenemedi (${esc(e.message)}).</div>`; }
  };
  if (el.open) ciz();
}
const bF = (d = 2) => v => ok(v) ? nf(v, d) : "—";
const bTL = v => ok(v) ? nf(v, 0) : "—";
const BI_SEG_AD = Object.fromEntries(BI_SEG.map(x => [x[0], x[1]])), BI_TUR_AD = { ...Object.fromEntries(BI_TUR.map(x => [x[0], x[1]])), bil: "Bilinmiyor" };

// ================================================================ BAP › KES
function biKesCiz() {
  const dates = biDates(), G = BI.g, i = dates.length - 1, son = dates[i];
  const segs = BS.seg;
  $("#bapBody").innerHTML = `<div class="chips biseg" id="kSeg" style="margin:0 0 12px">${BI_SEG.map(([k, l, c]) => `<button class="chip" data-s="${k}" aria-pressed="${segs.has(k)}"><i style="background:var(${c})"></i>${l}</button>`).join("")}</div>
    <div class="kpis bik" id="kKpi"></div>${biKart("kH")}${biKart("kY", `<div class="seg" id="kTur" role="group"></div>`)}${biKart("kE")}${biDetKart("kD")}`;
  $("#kSeg").onclick = e => { const b = e.target.closest("button[data-s]"); if (!b) return; const k = b.dataset.s; if (segs.has(k)) { if (segs.size > 1) segs.delete(k); } else segs.add(k); biKesCiz(); };
  // kutular
  const H = dates.map(d => biKes(G[d], segs).h), hf = biHafta(H, i), d1 = biCh(H[i], H[i - 1]);
  const j5 = biOnce(dates, i, 7), j30 = biOnce(dates, i, 30);
  const k = [biKpi("İşlem hacmi", biMr(H[i]), `günlük <b class="${cls(d1)}">${biPc(d1)}</b>`, gunAd(son) + " · seçili kıymetler, TL", "--c5", "",
    `<div class="s2">Haftalık (5 gün) <b>${biMr(hf.top, 0)}</b> · önceki haftaya göre <b class="${cls(hf.deg)}">${biPc(hf.deg)}</b></div>`)];
  for (const [t, ad, c] of BI_TUR) {
    const x = biKes(G[son], segs, t), dv = biDeger(x);
    // aynı ölçü (getiri ya da fiyat) ile 1 hafta ve 1 ay önceki değer
    const ol = j => { if (j < 0) return null; const y = biKes(G[dates[j]], segs, t); return dv?.tip === "getiri" ? y.y : y.p; };
    const tn = BI_TEN.map((l, q) => { const z = biKes(G[son], segs, t, q), v = dv?.tip === "getiri" ? z.y : z.p; return `<span><i>${l}</i>${ok(v) ? (dv.tip === "getiri" ? nf(v, 2) : nf(v, 2)) : "—"}</span>`; }).join("");
    k.push(biKpi(ad, dv ? (dv.tip === "getiri" ? pct(dv.v, 2) : nf(dv.v, 3)) : "—",
      dv ? `haftalık <b class="${cls(dv.v - ol(j5))}">${dv.ch(dv.v - ol(j5))}</b> · aylık <b class="${cls(dv.v - ol(j30))}">${dv.ch(dv.v - ol(j30))}</b>` : "Bu gün işlem yok",
      `${dv?.tip === "fiyat" ? "Ağ. ort. fiyat (getiri yayımlanmıyor)" : "Ağ. ort. bileşik getiri"} · hacim ${biMr(x.h)}`, c, ` data-t="${t}" role="button" tabindex="0" title="Grafikte göster"`,
      `<div class="bten">${tn}</div>`));
  }
  $("#kKpi").innerHTML = k.join("");
  $("#kKpi").onclick = e => { const b = e.target.closest("[data-t]"); if (b) { BS.kT = b.dataset.t; biKesCiz(); } };
  $$("#kKpi [data-t]").forEach(x => x.classList.toggle("sel", x.dataset.t === BS.kT));
  // hacim grafiği
  const ix = biAralik("kH", dates, biKesCiz, "3A"), xs = ix.map(j => dates[j]);
  $("#kHT").textContent = "Günlük işlem hacmi (milyon TL)"; $("#kHS").textContent = "Kesin alım satım pazarı (normal ve küçük emirler), TL kıymetler · çapraz ve özel işlem bildirimleri dahil";
  const sH = BI_SEG.filter(x => segs.has(x[0])).map(([s, l, c]) => ({ name: l, color: css(c), type: "bar", vals: xs.map(d => biKes(G[d], new Set([s])).h), fmt: v => nf(v, 0) + " mn ₺" }));
  biLeg("kH", sH); chart($("#kHG"), { xs, series: sH, stack: true, height: 280, xFmt: biX(ix), tipX: gunAd, yFmt: v => nf(v, 0), label: "KES işlem hacmi" });
  veriIS($("#kHV"), "kH", sH.map(s => s.name), xs[0], xs[xs.length - 1], sH.map(s => s.vals[0]), sH.map(s => s.vals[s.vals.length - 1]), v => nf(v, 0), (b, a) => biPc(biCh(b, a)), biKesCiz);
  // getiri / fiyat grafiği (seçili tür, vadeler)
  const T = BI_TUR.find(x => x[0] === BS.kT), dv0 = biDeger(biKes(G[son], segs, BS.kT)) || { tip: "getiri" }, gt = dv0.tip === "getiri";
  $("#kTur").innerHTML = BI_TUR.map(([k_, l]) => `<button data-k="${k_}" aria-pressed="${k_ === BS.kT}">${l.split(" ")[0].replace("TLREF", "TLREF/K")}</button>`).join("");
  $("#kTur").onclick = e => { const b = e.target.closest("button[data-k]"); if (b) { BS.kT = b.dataset.k; biKesCiz(); } };
  const iy = biAralik("kY", dates, biKesCiz, "3A"), xy = iy.map(j => dates[j]);
  $("#kYT").textContent = `${T[1]} · ${gt ? "ağırlıklı ortalama bileşik getiri (%)" : "ağırlıklı ortalama fiyat"}`;
  $("#kYS").textContent = `Vadeye kalan güne göre en yakın vade (1A ≤ 52 gün … 10Y > 2581 gün), hacim ağırlıklı · vadeye tıklayarak aç/kapat · işlem olmayan günler boş`;
  const tumu = { name: "Tümü", color: css(T[2]), width: 2.8, span: true, vals: xy.map(d => { const z = biKes(G[d], segs, BS.kT); return gt ? z.y : z.p; }), fmt: v => gt ? pct(v, 2) : nf(v, 3) };
  const sY = [tumu, ...BI_TEN.map((l, q) => [l, q]).filter(([, q]) => BS.kTen.has(String(q))).map(([l, q]) => ({ name: l, color: css(BI_TEN_COL[q]), width: 1.6, span: true,
    vals: xy.map(d => { const z = biKes(G[d], segs, BS.kT, q); return gt ? z.y : z.p; }), fmt: v => gt ? pct(v, 2) : nf(v, 3) }))];
  $("#kYL").innerHTML = BI_TEN.map((l, q) => `<button class="chip" data-q="${q}" aria-pressed="${BS.kTen.has(String(q))}"><i style="background:var(${BI_TEN_COL[q]})"></i>${l}</button>`).join("");
  $("#kYL").onclick = e => { const b = e.target.closest("button[data-q]"); if (!b) return; const q = b.dataset.q; BS.kTen.has(q) ? BS.kTen.delete(q) : BS.kTen.add(q); biKesCiz(); };
  chart($("#kYG"), { xs: xy, series: sY, height: 300, xFmt: biX(iy), tipX: gunAd, yFmt: v => nf(v, 1), label: $("#kYT").textContent });
  const ilkV = sY.map(s => s.vals.find(ok)), sonV = sY.map(s => [...s.vals].reverse().find(ok));
  veriIS($("#kYV"), "kY", sY.map(s => s.name), xy[0], xy[xy.length - 1], ilkV, sonV, v => gt ? pct(v, 2) : nf(v, 3), (b, a) => gt ? bp(b - a) : nf(b - a, 3), biKesCiz);
  // getiri eğrisi: son gün, 1 hafta ve 1 ay önce
  $("#kET").textContent = `${T[1]} · vadelere göre ${gt ? "getiri eğrisi" : "fiyat"}`; $("#kES").textContent = "Son işlem günü ile 1 hafta ve 1 ay önceki işlem günleri · işlem olmayan vadeler boş";
  $("#kER").innerHTML = "";
  const eg = [[i, "Son · " + gunKisa(son), "--c1", 2.6], [j5, "1 hafta önce", "--c3", 1.8], [j30, "1 ay önce", "--muted", 1.6]].filter(x => x[0] >= 0)
    .map(([j, l, c, w]) => ({ name: `${l}${j !== i ? " · " + gunKisa(dates[j]) : ""}`, color: css(c), width: w, dash: j === j30 ? "4 4" : undefined, span: true,
      vals: BI_TEN.map((_, q) => { const z = biKes(G[dates[j]], segs, BS.kT, q); return gt ? z.y : z.p; }), fmt: v => gt ? pct(v, 2) : nf(v, 3) }));
  biLeg("kE", eg); chart($("#kEG"), { xs: BI_TEN, series: eg, height: 260, xFmt: x => x, tipX: x => x, yFmt: v => nf(v, 1), label: $("#kET").textContent });
  $("#kEV").innerHTML = "";
  // detay
  biDetay("kD", dates, j => (j.bap || []).filter(r => r[0] === "kes"), () => [
    { a: "ISIN", f: v => `<b>${esc(v)}</b>`, v: r => r[2] }, { a: "İhraççı", v: r => BIK?.[r[2]]?.ih || (r[14] === "hdibs" || r[14] === "hsukuk" ? "Hazine" : "") },
    { a: "Tür", v: r => BI_SEG_AD[r[14]] || r[14] }, { a: "Getiri türü", v: r => BI_TUR_AD[r[15]] || r[15] }, { a: "Valör", v: r => r[3], f: v => v ? gunKisa(v) : "—" },
    { a: "Vadeye kalan gün", n: 1, v: r => r[6], f: bF(0) }, { a: "Para", v: r => r[5] }, { a: "AOF", n: 1, v: r => r[7], f: bF(3) }, { a: "Kapanış", n: 1, v: r => r[8], f: bF(3) },
    { a: "Basit getiri %", n: 1, v: r => r[9], f: bF(2) }, { a: "Bileşik getiri %", n: 1, v: r => r[10], f: bF(2) }, { a: "Hacim", n: 1, v: r => r[11], f: bTL },
    { a: "Nominal", n: 1, v: r => r[12], f: bTL }, { a: "İşlem", n: 1, v: r => r[13], f: bF(0) }], "bist-kes");
}

// ================================================================ BAP › repo türü pazarlar (oran + hacim)
function biPzSeri(dates, pz, cur = "TRY") { return dates.map(d => { const g = BI.g[d]; return g?.pz?.[pz]?.[cur] ?? (cur === "TRY" ? g?.m?.[pz]?.h : null) ?? null; }); }
function biOranPazar(pzler, baslik, aciklama) {
  const dates = biDates(), G = BI.g, i = dates.length - 1, son = dates[i], j5 = biOnce(dates, i, 7), j30 = biOnce(dates, i, 30);
  $("#bapBody").innerHTML = `<div class="kpis" id="pKpi2"></div>${biKart("pO")}${biKart("pH")}${biDetKart("pD")}`;
  const k = [];
  pzler.forEach(([pz, ad, c], q) => {
    const R = dates.map(d => G[d]?.m?.[pz]?.ron ?? G[d]?.m?.[pz]?.r ?? null), H = biPzSeri(dates, pz), hf = biHafta(H, i), r = R[i];
    if (!H.some(ok) && !R.some(ok)) return;
    if (R.some(ok)) k.push(biKpi(`${ad} · oran`, ok(r) ? pct(r, 2) : "—", ok(r) ? `günlük <b class="${cls(r - R[i - 1])}">${bp(r - R[i - 1])}</b> · haftalık <b class="${cls(r - R[j5])}">${bp(r - R[j5])}</b> · aylık <b class="${cls(r - R[j30])}">${bp(r - R[j30])}</b>` : "bu gün oranlı işlem yok",
      `${gunAd(son)} · gecelik (≤ 4 gün) ağırlıklı ortalama`, c));
    k.push(biKpi(`${ad} · hacim`, biMr(H[i]), `günlük <b class="${cls(biCh(H[i], H[i - 1]))}">${biPc(biCh(H[i], H[i - 1]))}</b> · işlem ${nf(G[son]?.m?.[pz]?.n || 0, 0)}`,
      `${gunAd(son)}`, c, "", `<div class="s2">Haftalık (5 gün) <b>${biMr(hf.top, 0)}</b> · önceki haftaya göre <b class="${cls(hf.deg)}">${biPc(hf.deg)}</b></div>`));
  });
  $("#pKpi2").innerHTML = k.join("") || `<div class="empty">Bu pazarda seçili dönemde işlem yok.</div>`;
  const io = biAralik("pO", dates, () => biOranPazar(pzler, baslik, aciklama), "6A"), xo = io.map(j => dates[j]);
  $("#pOT").textContent = `${baslik} · ağırlıklı ortalama oran (%)`; $("#pOS").textContent = aciklama + " · karşılaştırma için TLREF";
  const tl = D?.tlref ? (() => { const m = new Map(D.tlref.dates.map((d, j) => [d, D.tlref.rate[j]])); return xo.map(d => m.get(d) ?? null); })() : [];
  const sO = pzler.map(([pz, ad, c]) => ({ name: ad, color: css(c), width: 2.2, span: true, vals: xo.map(d => G[d]?.m?.[pz]?.ron ?? G[d]?.m?.[pz]?.r ?? null), fmt: v => pct(v, 2) })).filter(s => s.vals.some(ok));
  if (tl.some(ok) && sO.length) sO.push({ name: "TLREF", color: css("--muted"), width: 1.4, dash: "4 4", span: true, vals: tl, fmt: v => pct(v, 2) });
  biLeg("pO", sO); chart($("#pOG"), { xs: xo, series: sO, height: 280, xFmt: biX(io), tipX: gunAd, yFmt: v => nf(v, 0), label: $("#pOT").textContent });
  veriIS($("#pOV"), "pO", sO.map(s => s.name), xo[0], xo[xo.length - 1], sO.map(s => s.vals.find(ok)), sO.map(s => [...s.vals].reverse().find(ok)), v => pct(v, 2), (b, a) => bp(b - a), () => biOranPazar(pzler, baslik, aciklama));
  const ih = biAralik("pH", dates, () => biOranPazar(pzler, baslik, aciklama), "6A"), xh = ih.map(j => dates[j]);
  $("#pHT").textContent = `${baslik} · günlük işlem hacmi (milyar TL)`; $("#pHS").textContent = "Piyasa özet bülteni (tüm vadeler, çapraz işlemler dahil)";
  const sH = pzler.map(([pz, ad, c]) => ({ name: ad, color: css(c), type: "bar", vals: xh.map(d => { const v = biPzSeri([d], pz)[0]; return ok(v) ? v / 1e3 : null; }), fmt: v => nf(v, 1) + " mr ₺" })).filter(s => s.vals.some(ok));
  biLeg("pH", sH); chart($("#pHG"), { xs: xh, series: sH, stack: true, height: 260, xFmt: biX(ih), tipX: gunAd, yFmt: v => nf(v, 0), label: $("#pHT").textContent });
  veriIS($("#pHV"), "pH", sH.map(s => s.name), xh[0], xh[xh.length - 1], sH.map(s => s.vals[0]), sH.map(s => s.vals[s.vals.length - 1]), v => nf(v, 1), (b, a) => biPc(biCh(b, a)), () => biOranPazar(pzler, baslik, aciklama));
  const set = new Set(pzler.map(x => x[0]));
  biDetay("pD", dates, j => (j.bap || []).filter(r => set.has(r[0])), () => [
    { a: "Pazar", v: r => BI_PZ_AD[r[0]] || r[0] }, { a: "İşlem kodu", v: r => r[1], f: v => `<b>${esc(v)}</b>` }, { a: "Kıymet", v: r => r[2] }, { a: "Valör 1", v: r => r[3], f: v => v ? gunKisa(v) : "—" },
    { a: "Valör 2", v: r => r[4], f: v => v ? gunKisa(v) : "—" }, { a: "Vade (gün)", n: 1, v: r => r[6], f: bF(0) }, { a: "Para", v: r => r[5] }, { a: "AOF / oran", n: 1, v: r => r[7], f: bF(2) },
    { a: "Kapanış", n: 1, v: r => r[8], f: bF(2) }, { a: "Hacim", n: 1, v: r => r[11], f: bTL }, { a: "Nominal", n: 1, v: r => r[12], f: bTL }, { a: "İşlem", n: 1, v: r => r[13], f: bF(0) }], "bist-" + pzler[0][0]);
}

// ================================================================ BAP › para swap
function biSwapCiz() {
  const dates = biDates(), G = BI.g, i = dates.length - 1, son = dates[i], j5 = biOnce(dates, i, 7), j30 = biOnce(dates, i, 30);
  const CF = [["USDTRY", "USD/TRY", "--c1", "SOFR"], ["EURTRY", "EUR/TRY", "--c3", "€STR"]];
  const S_ = Object.fromEntries(CF.map(([c]) => [c, dates.map(d => biSwapGun(G[d], c, d))]));
  $("#bapBody").innerHTML = `<div class="kpis" id="sKpi"></div>${biKart("sO")}${biKart("sH")}${biDetKart("sD")}`;
  const k = [];
  for (const [c, ad, col, ref] of CF) {
    const A = S_[c], x = A[i], on = x.on, r = dates.map((_, j) => A[j].on?.r ?? null), H = dates.map((_, j) => (A[j].on?.h || 0) + A[j].dh || null), hf = biHafta(H, i);
    k.push(biKpi(`${ad} swap · O/N`, on && ok(on.r) ? pct(on.r, 2) : "—",
      on ? `günlük <b class="${cls(on.r - r[i - 1])}">${bp(on.r - r[i - 1])}</b> · haftalık <b class="${cls(on.r - r[j5])}">${bp(on.r - r[j5])}</b> · aylık <b class="${cls(on.r - r[j30])}">${bp(on.r - r[j30])}</b>` : "bu gün O/N işlem yok",
      on ? `TL implied (${ref} ile) · ${on.gun} gün · swap puanı ${nf(on.puan, 2)} · kur ${nf(on.spot, 4)} · ${gunAd(son)}` : gunAd(son), col, "",
      `<div class="s2">O/N hacim <b>${on ? biMr(on.h) : "—"}</b></div>`));
    k.push(biKpi(`${ad} swap · diğer vadeler`, ok(x.dr) ? pct(x.dr, 2) : "—", `hacim <b>${biMr(x.dh)}</b> · ${nf(Math.max(0, x.n - (on ? 1 : 0)), 0)} vade`,
      `Hacim ağırlıklı TL implied · ${ref} vadeye göre`, col, "", `<div class="s2">Haftalık toplam hacim <b>${biMr(hf.top, 0)}</b> · önceki haftaya göre <b class="${cls(hf.deg)}">${biPc(hf.deg)}</b></div>`));
  }
  $("#sKpi").innerHTML = k.join("");
  const io = biAralik("sO", dates, biSwapCiz, "6A"), xo = io.map(j => dates[j]);
  $("#sOT").textContent = "Para swap pazarı · TL implied oran (%)"; $("#sOS").textContent = "Swap puanı ve kurdan, ilgili vadedeki SOFR / €STR (Bloomberg OIS) ile hesaplanan TL getirisi · karşılaştırma için TLREF";
  const tl = D?.tlref ? (() => { const m = new Map(D.tlref.dates.map((d, j) => [d, D.tlref.rate[j]])); return xo.map(d => m.get(d) ?? null); })() : [];
  const sO = CF.flatMap(([c, ad, col]) => [{ name: `${ad} O/N`, color: css(col), width: 2.2, span: true, vals: io.map(j => S_[c][j].on?.r ?? null), fmt: v => pct(v, 2) },
    { name: `${ad} diğer vadeler`, color: css(col), width: 1.4, dash: "3 3", span: true, vals: io.map(j => S_[c][j].dr), fmt: v => pct(v, 2) }]).filter(s => s.vals.some(ok));
  if (tl.some(ok)) sO.push({ name: "TLREF", color: css("--muted"), width: 1.2, dash: "5 4", span: true, vals: tl, fmt: v => pct(v, 2) });
  biLeg("sO", sO); chart($("#sOG"), { xs: xo, series: sO, height: 290, xFmt: biX(io), tipX: gunAd, yFmt: v => nf(v, 0), label: $("#sOT").textContent });
  veriIS($("#sOV"), "sO", sO.map(s => s.name), xo[0], xo[xo.length - 1], sO.map(s => s.vals.find(ok)), sO.map(s => [...s.vals].reverse().find(ok)), v => pct(v, 2), (b, a) => bp(b - a), biSwapCiz);
  const ih = biAralik("sH", dates, biSwapCiz, "6A"), xh = ih.map(j => dates[j]);
  $("#sHT").textContent = "Para swap pazarı · günlük işlem hacmi (milyar TL)"; $("#sHS").textContent = "O/N ve diğer vadeler, döviz cinsine göre";
  const sH = CF.flatMap(([c, ad, col]) => [{ name: `${ad} O/N`, color: css(col), type: "bar", vals: ih.map(j => S_[c][j].on ? S_[c][j].on.h / 1e3 : null), fmt: v => nf(v, 1) + " mr ₺" },
    { name: `${ad} diğer`, color: css(col === "--c1" ? "--c5" : "--c6"), type: "bar", vals: ih.map(j => S_[c][j].dh ? S_[c][j].dh / 1e3 : null), fmt: v => nf(v, 1) + " mr ₺" }]).filter(s => s.vals.some(ok));
  biLeg("sH", sH); chart($("#sHG"), { xs: xh, series: sH, stack: true, height: 260, xFmt: biX(ih), tipX: gunAd, yFmt: v => nf(v, 0), label: $("#sHT").textContent });
  veriIS($("#sHV"), "sH", sH.map(s => s.name), xh[0], xh[xh.length - 1], sH.map(s => s.vals[0]), sH.map(s => s.vals[s.vals.length - 1]), v => nf(v, 1), (b, a) => biPc(biCh(b, a)), biSwapCiz);
  biDetay("sD", dates, j => (j.bap || []).filter(r => r[0] === "fxsw"), t => [
    { a: "İşlem kodu", v: r => r[1], f: v => `<b>${esc(v)}</b>` }, { a: "Parite", v: r => r[2].replace("_SWAP", "") }, { a: "Valör 1", v: r => r[3], f: v => v ? gunKisa(v) : "—" },
    { a: "Valör 2", v: r => r[4], f: v => v ? gunKisa(v) : "—" }, { a: "Vade (gün)", n: 1, v: r => r[6], f: bF(0) }, { a: "Swap puanı", n: 1, v: r => r[7], f: bF(2) },
    { a: "Kur", n: 1, v: r => r[9], f: bF(4) }, { a: "SOFR / €STR %", n: 1, v: r => biOis(r[2].startsWith("EUR") ? "EUR" : "USD", t, r[6]), f: bF(2) },
    { a: "TL implied %", n: 1, v: r => biImplied(r[2], t, r[6], r[7], r[9]), f: bF(2) }, { a: "Hacim (TL)", n: 1, v: r => r[11], f: bTL }, { a: "Döviz tutarı", n: 1, v: r => r[12], f: bTL }, { a: "İşlem", n: 1, v: r => r[13], f: bF(0) }], "bist-swap");
}

// ================================================================ BAP › yalnızca hacim olan pazarlar
function biHacimPazar(pz, ad, aciklama, cur = "TRY") {
  const dates = biDates(), G = BI.g, i = dates.length - 1, son = dates[i];
  $("#bapBody").innerHTML = `<div class="kpis" id="hKpi"></div>${biKart("hH")}${biDetKart("hD")}`;
  const H = biPzSeri(dates, pz, cur), hf = biHafta(H, i), birim = cur === "TRY" ? v => biMr(v) : v => ok(v) ? `${nf(v, 1)} mn ${cur}` : "—";
  const R = dates.map(d => G[d]?.m?.[pz]?.r ?? null);
  $("#hKpi").innerHTML = biKpi(`${ad} · hacim`, birim(H[i]), `günlük <b class="${cls(biCh(H[i], H[i - 1]))}">${biPc(biCh(H[i], H[i - 1]))}</b> · işlem ${nf(G[son]?.m?.[pz]?.n || 0, 0)}`, gunAd(son), "--c1", "",
      `<div class="s2">Haftalık (5 gün) <b>${birim(hf.top)}</b> · önceki haftaya göre <b class="${cls(hf.deg)}">${biPc(hf.deg)}</b></div>`)
    + (R.some(ok) ? biKpi(`${ad} · oran`, pct(R[i], 2), "hacim ağırlıklı", gunAd(son), "--c3") : "")
    + biKpi("Son 1 ay toplam", birim((() => { const j = biOnce(dates, i, 30); let t = 0; for (let q = j + 1; q <= i; q++) if (ok(H[q])) t += H[q]; return t; })()), "", "son 30 gün", "--c6");
  const ih = biAralik("hH", dates, () => biHacimPazar(pz, ad, aciklama, cur), "6A"), xh = ih.map(j => dates[j]);
  $("#hHT").textContent = `${ad} · günlük işlem hacmi (${cur === "TRY" ? "milyon TL" : "milyon " + cur})`; $("#hHS").textContent = aciklama;
  const sH = [{ name: ad, color: css("--c1"), type: "bar", vals: ih.map(j => H[j]), fmt: v => nf(v, 1) }];
  if (R.some(ok)) sH.push({ name: "Oran (%)", color: css("--c3"), width: 2, axis: "r", span: true, vals: ih.map(j => R[j]), fmt: v => pct(v, 2) });
  biLeg("hH", sH); chart($("#hHG"), { xs: xh, series: sH, height: 280, xFmt: biX(ih), tipX: gunAd, yFmt: v => nf(v, 0), y2Fmt: v => nf(v, 0), label: $("#hHT").textContent });
  veriIS($("#hHV"), "hH", [ad], xh[0], xh[xh.length - 1], [sH[0].vals[0]], [sH[0].vals[sH[0].vals.length - 1]], v => nf(v, 1), (b, a) => biPc(biCh(b, a)), () => biHacimPazar(pz, ad, aciklama, cur));
  biDetay("hD", dates, j => (j.bap || []).filter(r => r[0] === pz), () => [
    { a: "İşlem kodu", v: r => r[1], f: v => `<b>${esc(v)}</b>` }, { a: "Kıymet", v: r => r[2] }, { a: "Valör 1", v: r => r[3], f: v => v ? gunKisa(v) : "—" },
    { a: "Valör 2", v: r => r[4], f: v => v ? gunKisa(v) : "—" }, { a: "Vade (gün)", n: 1, v: r => r[6], f: bF(0) }, { a: "Para", v: r => r[5] }, { a: "AOF / oran", n: 1, v: r => r[7], f: bF(2) },
    { a: "İkinci fiyat", n: 1, v: r => r[9], f: bF(2) }, { a: "Hacim", n: 1, v: r => r[11], f: bTL }, { a: "Nominal / miktar", n: 1, v: r => r[12], f: bTL }, { a: "İşlem", n: 1, v: r => r[13], f: bF(0) }], "bist-" + pz);
}

// ================================================================ KMTP
function biKmpCiz() {
  const dates = biKmDates(), K = BI.km, i = dates.length - 1, son = dates[i], j5 = biOnce(dates, i, 7), j30 = biOnce(dates, i, 30);
  if (!dates.length) { $("#kmpBody").innerHTML = `<div class="empty">KMTP bülteni henüz derlenmedi.</div>`; return; }
  $("#kmpBody").innerHTML = `<div class="kpis" id="mKpi"></div>${biKart("mH")}${biKart("mF", `<div class="seg" id="mFm" role="group"></div>`)}${biDetKart("mD")}`;
  const k = [];
  for (const [m, ad, c] of BI_MET) {
    const H = dates.map(d => K[d]?.[m]?.h ?? null), hf = biHafta(H, i), F = dates.map(d => K[d]?.[m]?.aofu ?? null), FT = dates.map(d => K[d]?.[m]?.aof ?? null);
    if (!H.slice(-22).some(v => v > 0)) continue;          // son bir ayda işlem görmeyen madenleri gösterme
    k.push(biKpi(`${ad} · işlem hacmi`, biMr(H[i]), `günlük <b class="${cls(biCh(H[i], H[i - 1]))}">${biPc(biCh(H[i], H[i - 1]))}</b> · ${nf(K[son]?.[m]?.kg || 0, 0)} kg · ${nf(K[son]?.[m]?.n || 0, 0)} işlem`,
      `${gunAd(son)} · tüm para birimleri, TL karşılığı`, c, "", `<div class="s2">Haftalık (5 gün) <b>${biMr(hf.top, 0)}</b> · önceki haftaya göre <b class="${cls(hf.deg)}">${biPc(hf.deg)}</b></div>`));
    if (m === "au" || m === "ag") k.push(biKpi(`${ad} · fiyat (USD/ons)`, ok(F[i]) ? nf(F[i], 2) : "—",
      `haftalık <b class="${cls(biCh(F[i], F[j5]))}">${biPc(biCh(F[i], F[j5]))}</b> · aylık <b class="${cls(biCh(F[i], F[j30]))}">${biPc(biCh(F[i], F[j30]))}</b>`,
      `${ok(FT[i]) ? `TL/kg ${nf(FT[i], 0)} · ` : ""}Borsa İstanbul metal fiyatı (AOF)`, c));
  }
  $("#mKpi").innerHTML = k.join("");
  const ih = biAralik("mH", dates, biKmpCiz, "6A"), xh = ih.map(j => dates[j]);
  $("#mHT").textContent = "Günlük işlem hacmi (milyon TL)"; $("#mHS").textContent = `Kıymetli madenler piyasası, madenlere göre · TL, USD ve EUR işlemler TL karşılığıyla · USD/TRY ${nf(K[son]?.usd || 0, 4)}`;
  const sH = BI_MET.map(([m, ad, c]) => ({ name: ad, color: css(c), type: "bar", vals: xh.map(d => K[d]?.[m]?.h ?? null), fmt: v => nf(v, 0) + " mn ₺" })).filter(s => s.vals.some(v => v > 0));
  biLeg("mH", sH); chart($("#mHG"), { xs: xh, series: sH, stack: true, height: 280, xFmt: biX(ih), tipX: gunAd, yFmt: v => nf(v, 0), label: "KMTP işlem hacmi" });
  veriIS($("#mHV"), "mH", sH.map(s => s.name), xh[0], xh[xh.length - 1], sH.map(s => s.vals[0]), sH.map(s => s.vals[s.vals.length - 1]), v => nf(v, 0), (b, a) => biPc(biCh(b, a)), biKmpCiz);
  BS.mF ||= "au";
  $("#mFm").innerHTML = BI_MET.filter(([m]) => dates.some(d => K[d]?.[m]?.aofu)).map(([m, ad]) => `<button data-k="${m}" aria-pressed="${m === BS.mF}">${ad}</button>`).join("");
  $("#mFm").onclick = e => { const b = e.target.closest("button[data-k]"); if (b) { BS.mF = b.dataset.k; biKmpCiz(); } };
  const ifx = biAralik("mF", dates, biKmpCiz, "6A"), xf = ifx.map(j => dates[j]), MA = BI_MET.find(x => x[0] === BS.mF);
  $("#mFT").textContent = `${MA[1]} · Borsa İstanbul fiyatı`; $("#mFS").textContent = "Ağırlıklı ortalama metal fiyatı: USD/ons (sol) ve TL/kg (sağ)";
  const sF = [{ name: "USD/ons", color: css(MA[2]), width: 2.4, span: true, vals: xf.map(d => K[d]?.[BS.mF]?.aofu ?? null), fmt: v => nf(v, 2) },
    { name: "TL/kg", color: css("--c1"), width: 1.6, axis: "r", span: true, vals: xf.map(d => K[d]?.[BS.mF]?.aof ?? null), fmt: v => nf(v, 0) }];
  biLeg("mF", sF); chart($("#mFG"), { xs: xf, series: sF, height: 260, xFmt: biX(ifx), tipX: gunAd, yFmt: v => nf(v, 0), y2Fmt: v => nf(v / 1e3, 0) + "b", label: $("#mFT").textContent });
  veriIS($("#mFV"), "mF", sF.map(s => s.name), xf[0], xf[xf.length - 1], sF.map(s => s.vals.find(ok)), sF.map(s => [...s.vals].reverse().find(ok)), (v, q) => nf(v, q ? 0 : 2), (b, a) => biPc(biCh(b, a)), biKmpCiz);
  biDetay("mD", dates, j => j.kmp || [], () => [
    { a: "Seri", v: r => r[0], f: v => `<b>${esc(v)}</b>` }, { a: "Maden", v: r => r[1] }, { a: "Pazar", v: r => r[2] }, { a: "Fiyat birimi", v: r => r[3] }, { a: "Ayar", n: 1, v: r => r[4], f: bF(2) },
    { a: "Takas", v: r => r[5] }, { a: "Adet", n: 1, v: r => r[6], f: bF(0) }, { a: "TL hacim", n: 1, v: r => r[7], f: bTL }, { a: "USD hacim", n: 1, v: r => r[8], f: bTL },
    { a: "İşlem", n: 1, v: r => r[9], f: bF(0) }, { a: "AOF", n: 1, v: r => r[10], f: bF(2) }, { a: "En düşük", n: 1, v: r => r[11], f: bF(2) }, { a: "En yüksek", n: 1, v: r => r[12], f: bF(2) },
    { a: "Kapanış", n: 1, v: r => r[13], f: bF(2) }], "bist-kmtp");
}

// ================================================================ dağıtım
function renderBist() {
  $$("#biTabs button").forEach(b => b.setAttribute("aria-pressed", b.dataset.b === BS.b));
  $("#biBap").classList.toggle("hidden", BS.b !== "bap"); $("#biKmp").classList.toggle("hidden", BS.b !== "kmp");
  const g = $("#biGate");
  if (BI === undefined) { g.classList.remove("hidden"); g.textContent = "BIST bülten verisi yükleniyor…"; biYukle(); return; }
  if (!BI || !biDates().length) { g.classList.remove("hidden"); g.textContent = "BIST bülten verisi henüz derlenmedi; ilk derleme 2025 başından itibaren birkaç çalışmada tamamlanır."; return; }
  g.classList.toggle("hidden", !BI.eksik); g.textContent = BI.eksik ? `Geçmiş veriler tamamlanıyor: ${nf(BI.eksik, 0)} iş günü kaldı (her güncellemede eklenir).` : "";
  try {
    if (BS.b === "kmp") biKmpCiz();
    else {
      const dates = biDates(), var_ = new Set(dates.slice(-120).flatMap(d => [...Object.keys(BI.g[d].pz || {}), ...Object.keys(BI.g[d].m || {}), ...(BI.g[d].k?.length ? ["kes"] : []), ...(Object.keys(BI.g[d].sw || {}).length ? ["fxsw"] : [])]));
      const tabs = BI_PZ.filter(([k]) => k === "kes" || var_.has(k) || (k === "repo" && var_.has("repos")));
      if (!tabs.some(x => x[0] === BS.m)) BS.m = "kes";
      $("#bapTabs").innerHTML = tabs.map(([k, l]) => `<button data-m="${k}" aria-pressed="${k === BS.m}">${l}</button>`).join("");
      if (BS.m === "kes") biKesCiz();
      else if (BS.m === "repo") biOranPazar([["repo", "Repo-T.Repo (normal emir)", "--c1"], ["repos", "Repo-T.Repo (küçük emir)", "--c6"]], "Repo-Ters Repo Pazarı", "Devlet iç borçlanma senetleri karşılığı repo · gecelik oran");
      else if (BS.m === "brep") biOranPazar([["brep", "Bankalararası repo", "--c1"]], "Bankalararası Repo Pazarı", "Bankalararası repo işlemleri");
      else if (BS.m === "ctm") biOranPazar([["ctm", "Taahhütlü işlem", "--c3"]], "Taahhütlü İşlem Pazarı", "Kira sertifikası karşılığı taahhütlü işlemler (sukuk repo)");
      else if (BS.m === "fxsw") biSwapCiz();
      else if (BS.m === "kmsw") biHacimPazar("kmsw", "KM swap", "Kıymetli madenler swap pazarı", "USD");
      else biHacimPazar(BS.m, BI_PZ.find(x => x[0] === BS.m)[1], { mktr: "Menkul kıymet tercihli repo (özel sektör borçlanma araçları karşılığı)", prep: "Pay senedi karşılığı repo", para: "Borsa İstanbul Para Piyasası (teminatlı borç verme / alma)", ihrac: "Nitelikli yatırımcıya ihraç pazarı" }[BS.m] || "");
    }
  } catch (e) { console.error(e); }
}
let biYuk;
function biYukle() { biYuk ||= fetch("data/bist.json?t=" + Date.now(), { cache: "no-store" }).then(r => r.ok ? r.json() : null).catch(() => null).then(j => { BI = j; if (S.tab === "piyasa" && S.ps === "bist") { renderBist(); renderSrc(); } }); }
$("#biTabs").onclick = e => { const b = e.target.closest("button[data-b]"); if (b) { BS.b = b.dataset.b; renderBist(); } };
$("#bapTabs").onclick = e => { const b = e.target.closest("button[data-m]"); if (b) { BS.m = b.dataset.m; renderBist(); } };
