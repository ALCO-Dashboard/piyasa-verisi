// =============================================================== para politikası (TCMB › Para Politikası)
// Veri: data/politika.enc.json (bankacilik/guncelle.py › politika): EVDS bie_apifon + bie_swaptektarf + USD/TRY,
// TÜFE endeksi (TP.FG.J0), TCMB 1 hafta repo tarihçesi ve PPK takvimi.
const PPS = { sel: null, range: "2Y", drange: "1Y", ppkYear: null, ppkChart: false };
// TÜFE yıllık: Makro Veriler'deki TÜİK serisi (makro.json); yoksa EVDS TÜFE endeksinden hesaplanır
let PP_TUFE = null;
fetch("../makro/data/makro.json?t=" + Date.now(), { cache: "no-store" }).then(r => r.ok ? r.json() : null).catch(() => null).then(j => {
  const t = j?.tufe; if (!t?.months) return;
  PP_TUFE = {}; t.months.forEach((ay, i) => { if (ok(t.yoy[i])) PP_TUFE[ay] = t.yoy[i]; });
  const pane = $("#ppPane"); if (pane && !pane.classList.contains("hidden")) ppRender();
});
const PP_SW = ["sw_usd_piy", "sw_usd_bist", "sw_usd_al", "sw_usd_sat", "sw_usd_mik", "sw_xau_piy", "sw_xau_al", "sw_xau_sat", "sw_top_al", "sw_top_sat"];
function ppModel() {
  const P = D.p; if (!P || !P.daily || !P.daily.dates || !P.daily.dates.length) return null;
  if (P._m) return P._m;
  const dt = P.daily.dates, s = P.daily.series, n = dt.length;
  const ff = a => { const o = []; let l = null; for (let i = 0; i < n; i++) { if (a && ok(a[i])) l = a[i]; o.push(l); } return o; };
  const kur = ff(s.usdtry), sw = {}; PP_SW.forEach(k => sw[k] = ff(s[k]));
  const v = (k, i) => sw[k][i] || 0;
  const M = {};
  M.fon = s.fon_top || []; M.st = s.st_top || [];
  ["fon_iha", "fon_bist", "fon_tldepo", "fon_glp", "st_iha", "st_kot", "st_lik", "aof"].forEach(k => M[k] = s[k] || []);
  M.net = dt.map((_, i) => ok(M.fon[i]) && ok(M.st[i]) ? M.fon[i] - M.st[i] : (s.net && ok(s.net[i]) ? s.net[i] : null));
  M.sw_usd = dt.map((_, i) => kur[i] ? (v("sw_usd_piy", i) + v("sw_usd_bist", i) + v("sw_usd_al", i) + v("sw_usd_mik", i) - v("sw_usd_sat", i)) * kur[i] : null);
  M.sw_xau = dt.map((_, i) => kur[i] ? (v("sw_xau_piy", i) + v("sw_xau_al", i) - v("sw_xau_sat", i)) * kur[i] : null);
  M.swap = dt.map((_, i) => kur[i] && (ok(sw.sw_top_al[i]) || ok(sw.sw_top_sat[i])) ? (v("sw_top_al", i) - v("sw_top_sat", i)) * kur[i] : null);
  M.sw_dig = dt.map((_, i) => ok(M.swap[i]) ? M.swap[i] - (M.sw_usd[i] || 0) - (M.sw_xau[i] || 0) : null);
  M.nets = dt.map((_, i) => ok(M.net[i]) && ok(M.swap[i]) ? M.net[i] + M.swap[i] : null);
  M.st_neg = M.st.map(x => ok(x) ? -x : null);
  const F = (P.faiz || []).slice().sort((a, b) => a.tarih < b.tarih ? -1 : 1);
  const rateAt = d => { let r = null; for (const f of F) { if (f.tarih <= d) r = f.oran; else break; } return r; };
  M.pol = dt.map(d => rateAt(d));
  let last = n - 1; while (last > 0 && !ok(M.fon[last]) && !ok(M.st[last])) last--;
  return P._m = { dt, M, kur, sw, F, rateAt, last, n };
}
const ppMr = v => !ok(v) ? "—" : (v < 0 ? "−" : "") + (Math.abs(v) >= 1e6 ? `₺${nf(2).format(Math.abs(v) / 1e6)} tr` : `₺${nf(Math.abs(v) >= 1e5 ? 0 : 1).format(Math.abs(v) / 1e3)} mr`);
const ppPct = (v, d = 1) => !ok(v) ? "—" : `%${nf(d).format(v)}`;
const PP_BOX = [
  { k: "fon", lab: "Para Piyasaları ile Fonlama", c: 1 }, "−",
  { k: "st", lab: "Toplam Sterilizasyon", c: 8 }, "=",
  { k: "net", lab: "Net Fonlama", c: 3 }, "+",
  { k: "swap", lab: "Toplam Swap Fonlama", c: 2 }, "=",
  { k: "nets", lab: "Swap Dahil Net Fonlama", c: 7 }, "|",
  { k: "aof", lab: "TCMB AOF", c: 4, rate: true }];
// kutunun altındaki oran: o kalemin içindeki payı ya da ilişkili oran
function ppBoxSub(k, m, i) {
  const M = m.M, fon = M.fon[i], st = M.st[i];
  if (k === "fon") return ok(fon) && ok(st) && fon + st ? `Brüt TCMB işlemlerinin ${ppPct(fon / (fon + st) * 100)}’i` : "";
  if (k === "st") return ok(fon) && ok(st) && fon + st ? `Brüt TCMB işlemlerinin ${ppPct(st / (fon + st) * 100)}’i` : "";
  if (k === "net") return ok(fon) && ok(st) && st ? `Fonlama / sterilizasyon: ${ppPct(fon / st * 100)}` : "";
  if (k === "swap") { const u = M.sw_usd[i], x = M.sw_xau[i], t = Math.abs(u || 0) + Math.abs(x || 0); return t ? `USDTRY ${ppPct(Math.abs(u || 0) / t * 100, 0)} · XAUTRY ${ppPct(Math.abs(x || 0) / t * 100, 0)}` : ""; }
  if (k === "nets") { const a = M.net[i], b = M.swap[i]; return ok(a) && ok(b) && (Math.abs(a) + Math.abs(b)) ? `Swap payı ${ppPct(Math.abs(b) / (Math.abs(a) + Math.abs(b)) * 100)}` : ""; }
  if (k === "aof") { const p = M.pol[i], a = M.aof[i]; return ok(p) && ok(a) ? `Politika faizi ${ppPct(p, 2)} · fark ${sgnOf(a - p, 2)}${nf(2).format(Math.abs(a - p))} puan` : ""; }
  return "";
}
function ppPrev(arr, i) { for (let j = i - 1; j >= 0; j--) if (ok(arr[j])) return arr[j]; return null; }
function ppBoxes(m) {
  const i = m.last, d = m.dt[i];
  return `<div class="ppboxes">` + PP_BOX.map(b => {
    if (typeof b === "string") return b === "|" ? `<span class="ppsep"></span>` : `<span class="ppop">${b}</span>`;
    const arr = m.M[b.k], v = arr[i], p = ppPrev(arr, i), dv = ok(v) && ok(p) ? v - p : null;
    const val = b.rate ? ppPct(v, 2) : ppMr(v);
    const chg = b.rate ? (ok(dv) ? `${sgnOf(dv, 2)}${nf(2).format(Math.abs(dv))} puan` : "") : (ok(dv) ? `${sgnOf(dv, 0)}${ppMr(Math.abs(dv))} (${fmtPct(pct(v, p))})` : "");
    return `<button type="button" class="ppbox" data-pp="${b.k}" aria-pressed="${PPS.sel === b.k}" style="--bc:var(--c${b.c})">
      <span class="pl">${esc(b.lab)}</span><span class="pv ${!b.rate && ok(v) && v < 0 ? "neg" : ""}">${val}</span>
      <span class="ps">${esc(ppBoxSub(b.k, m, i))}</span><span class="pd">${dShort(d)}${chg ? ` · günlük ${chg}` : ""}</span></button>`;
  }).join("") + `</div>`;
}
// grafik içi kırılım kutuları: tür · tutar · oran
const PP_PARTS = {
  fon: { title: "Para Piyasaları ile Fonlama", stacks: [["fon_iha", "İhale yoluyla (1 hafta vadeli repo · APİ)", 1], ["fon_bist", "BİST O/N repo · kotasyon · piyasa yapıcı repo", 2], ["fon_tldepo", "TL depo (kotasyon)", 3], ["fon_glp", "GLP depo / repo", 4]], line: "fon", base: "fon" },
  st: { title: "Toplam Sterilizasyon", stacks: [["st_iha", "İhale yoluyla (1 hafta vadeli depo)", 8], ["st_kot", "Kotasyon yoluyla (O/N depo · BİST O/N ters repo)", 5], ["st_lik", "Likidite senedi", 7]], line: "st", base: "st" },
  net: { title: "Net Fonlama", stacks: [["fon", "Para piyasaları ile fonlama", 1], ["st_neg", "Sterilizasyon", 8]], line: "net", base: null },
  swap: { title: "Toplam Swap Fonlama", stacks: [["sw_usd", "USDTRY swap (döviz karşılığı TL)", 1], ["sw_xau", "XAUTRY swap (altın karşılığı TL)", 4], ["sw_dig", "Diğer swap", 6]], line: "swap", base: "abs" },
  nets: { title: "Swap Dahil Net Fonlama", stacks: [["net", "Net fonlama", 3], ["swap", "Toplam swap fonlama", 2]], line: "nets", base: "abs" },
};
function ppPartTiles(m, key) {
  const i = m.last, M = m.M;
  if (key === "aof") {
    const a = M.aof[i], p = M.pol[i];
    return [["TCMB AOF", ppPct(a, 2), ""], ["Politika faizi (1 hafta repo)", ppPct(p, 2), ""], ["AOF − politika faizi", ok(a) && ok(p) ? `${sgnOf(a - p, 2)}${nf(2).format(Math.abs(a - p))} puan` : "—", ""]]
      .map(([t, v, r]) => `<div class="pptile"><span class="tt">${esc(t)}</span><b>${v}</b>${r ? `<span class="tr">${r}</span>` : ""}</div>`).join("");
  }
  const P = PP_PARTS[key];
  const vals = P.stacks.map(([k]) => M[k][i]);
  const base = P.base === "abs" ? vals.reduce((t, x) => t + Math.abs(x || 0), 0) : P.base ? M[P.base][i] : null;
  return P.stacks.map(([k, n, c], j) => {
    const v = vals[j]; if (k === "sw_dig" && (!ok(v) || Math.abs(v) < 1)) return "";
    const r = base ? (P.base === "abs" ? Math.abs(v || 0) : (v || 0)) / base * 100 : null;
    return `<div class="pptile" style="--bc:var(--c${c})"><span class="tt"><i></i>${esc(n)}</span><b class="${ok(v) && v < 0 ? "neg" : ""}">${ppMr(v)}</b>${ok(r) ? `<span class="tr">${ppPct(r)}</span>` : ""}</div>`;
  }).join("");
}
// yığılmış günlük çubuk + çizgi
function ppStackChart(el, { dates, stacks, line, height = 300 }) {
  el.innerHTML = "";
  const idx = dates.map((d, i) => i).filter(i => stacks.some(s => ok(s.vals[i])) || (line && ok(line.vals[i])));
  if (!idx.length) { el.innerHTML = '<div class="empty">Seçili dönemde veri yok.</div>'; return; }
  const lg = document.createElement("div"); lg.className = "legend";
  lg.innerHTML = stacks.map(s => `<span><i style="background:${s.color};height:10px;width:10px;border-radius:2px"></i>${esc(s.name)}</span>`).join("") + (line ? `<span><i style="background:${line.color}"></i>${esc(line.name)}</span>` : "");
  el.appendChild(lg);
  const box = el.appendChild(Object.assign(document.createElement("div"), { className: "chart" }));
  const W = Math.max(320, box.clientWidth || el.clientWidth || 640), H = height, m = { t: 12, r: 16, b: 26, l: 64 };
  let y0 = 0, y1 = 0;
  for (const i of idx) { let p = 0, q = 0; for (const s of stacks) { const v = s.vals[i]; if (!ok(v)) continue; if (v >= 0) p += v; else q += v; } y1 = Math.max(y1, p, line && ok(line.vals[i]) ? line.vals[i] : -Infinity); y0 = Math.min(y0, q, line && ok(line.vals[i]) ? line.vals[i] : Infinity); }
  if (y0 === y1) y1 = y0 + 1;
  const pad = (y1 - y0) * 0.06; y0 -= y0 < 0 ? pad : 0; y1 += pad;
  const ticks = niceTicks(y0, y1, 5); y0 = Math.min(y0, ticks[0]); y1 = Math.max(y1, ticks[ticks.length - 1]);
  const t0 = toTime(dates[idx[0]]), t1 = Math.max(t0 + 864e5, toTime(dates[idx[idx.length - 1]]));
  const X = t => m.l + (t - t0) / (t1 - t0) * (W - m.l - m.r), Y = y => m.t + (1 - (y - y0) / (y1 - y0)) * (H - m.t - m.b);
  const bw = Math.max(1, (W - m.l - m.r) / idx.length * 0.8);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Günlük grafik"><g class="axis">`;
  for (const t of ticks) svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(t)}" y2="${Y(t)}" stroke="var(--grid)"/><text x="${m.l - 8}" y="${Y(t) + 4}" text-anchor="end">${nf(Math.abs(y1 - y0) < 20 ? 1 : 0).format(t)}</text>`;
  const span = t1 - t0, nX = Math.max(2, Math.min(7, Math.floor((W - m.l) / 105)));
  for (let k = 0; k < nX; k++) { const t = t0 + span * k / (nX - 1), d = new Date(t); svg += `<text x="${X(t)}" y="${H - 6}" text-anchor="${k === 0 ? "start" : k === nX - 1 ? "end" : "middle"}">${span > 400 * 864e5 ? `${AY[d.getMonth()]} ${String(d.getFullYear()).slice(2)}` : `${d.getDate()} ${AY[d.getMonth()]}`}</text>`; }
  svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--axis)"/></g><g>`;
  for (const i of idx) {
    const x = X(toTime(dates[i])) - bw / 2; let p = 0, q = 0;
    for (const s of stacks) { const v = s.vals[i]; if (!ok(v) || v === 0) continue; const a = v >= 0 ? p : q, b = a + v; if (v >= 0) p = b; else q = b; svg += `<rect x="${x.toFixed(1)}" y="${Y(Math.max(a, b)).toFixed(1)}" width="${bw.toFixed(2)}" height="${Math.max(0.5, Math.abs(Y(a) - Y(b))).toFixed(1)}" fill="${s.color}" opacity=".85"/>`; }
  }
  svg += `</g>`;
  if (line) { let d = "", pen = false; for (const i of idx) { const v = line.vals[i]; if (!ok(v)) { pen = false; continue; } d += (pen ? "L" : "M") + X(toTime(dates[i])).toFixed(1) + " " + Y(v).toFixed(1); pen = true; } svg += `<path d="${d}" fill="none" stroke="${line.color}" stroke-width="2.2" stroke-linejoin="round"/>`; }
  svg += `<line class="xh" y1="${m.t}" y2="${H - m.b}" stroke="var(--axis)" stroke-dasharray="3 3" opacity="0"/><rect x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/></svg><div class="tip"></div>`;
  box.innerHTML = svg;
  const svgEl = box.querySelector("svg"), tip = box.querySelector(".tip"), xh = box.querySelector(".xh");
  svgEl.addEventListener("pointermove", ev => {
    const r = svgEl.getBoundingClientRect(), px = (ev.clientX - r.left) * (W / r.width), t = t0 + (px - m.l) / (W - m.l - m.r) * span;
    let best = idx[0]; for (const i of idx) { if (toTime(dates[i]) <= t + 0.5 * 864e5) best = i; else break; }
    const cx = X(toTime(dates[best])); xh.setAttribute("x1", cx); xh.setAttribute("x2", cx); xh.setAttribute("opacity", 1);
    tip.innerHTML = `<div class="d">${dLabel(dates[best])}</div>` + (line ? `<div class="r"><span><i style="background:${line.color}"></i>${esc(line.name)}</span><b>${nf(1).format(line.vals[best] ?? NaN)}</b></div>` : "")
      + stacks.map(s => ok(s.vals[best]) ? `<div class="r"><span><i style="background:${s.color}"></i>${esc(s.name)}</span><b>${nf(1).format(s.vals[best])}</b></div>` : "").join("");
    tip.style.opacity = 1; const bwid = box.clientWidth, tw = tip.offsetWidth, sx = cx * (r.width / W);
    tip.style.top = "6px"; tip.style.left = (sx + 14 + tw > bwid ? Math.max(0, sx - tw - 14) : sx + 14) + "px";
  });
  svgEl.addEventListener("pointerleave", () => { tip.style.opacity = 0; xh.setAttribute("opacity", 0); });
}
function ppClipIdx(m, key) { const days = (RANGES.find(r => r[0] === key) || [0, 1e7])[1]; const end = toTime(m.dt[m.last]), st = end - days * 864e5; return m.dt.map((d, i) => i).filter(i => i <= m.last && toTime(m.dt[i]) >= st); }
function ppDrawChart(m) {
  const host = $("#ppChart"); if (!host) return; const key = PPS.sel; if (!key) return;
  const ids = ppClipIdx(m, PPS.range), dates = ids.map(i => m.dt[i]), pal = PAL(), col = c => pal[(c - 1) % pal.length], M = m.M;
  if (key === "aof") {
    lineChart(host, { series: [
      { name: "TCMB AOF (%)", color: col(4), data: ids.map(i => [m.dt[i], ok(M.aof[i]) ? M.aof[i] : null, toTime(m.dt[i])]) },
      { name: "Politika faizi (%)", color: col(1), dash: true, data: ids.map(i => [m.dt[i], M.pol[i], toTime(m.dt[i])]) }], height: 300, yFmt: v => nf(2).format(v) });
    return;
  }
  const P = PP_PARTS[key];
  ppStackChart(host, { dates, height: 300,
    stacks: P.stacks.map(([k, n, c]) => ({ name: n, color: col(c), vals: ids.map(i => ok(M[k][i]) ? M[k][i] / 1e3 : null) })).filter(s => s.vals.some(v => ok(v) && Math.abs(v) > 0.001)),
    line: { name: P.title + " (net)", color: "var(--ink)", vals: ids.map(i => ok(M[P.line][i]) ? M[P.line][i] / 1e3 : null) } });
}
// ---------------- PPK
function ppkList(m) {
  const P = D.p, today = new Date().toISOString().slice(0, 10), out = [];
  for (const [y, arr] of Object.entries(P.ppk || {})) for (const x of arr) out.push({ ...x, yil: y });
  out.sort((a, b) => a.tarih < b.tarih ? -1 : 1);
  const F = m ? m.F : (P.faiz || []), rateAt = d => { let r = null; for (const f of F) { if (f.tarih <= d) r = f.oran; else break; } return r; };
  const plus = (d, k) => { const t = new Date(d + "T00:00:00"); t.setDate(t.getDate() + k); return t.toISOString().slice(0, 10); };
  const T = P.tufe || {}, yoy = ym => { const [y, mo] = ym.split("-").map(Number), p = `${y - 1}-${String(mo).padStart(2, "0")}`; return ok(T[ym]) && ok(T[p]) ? (T[ym] / T[p] - 1) * 100 : null; };
  for (const x of out) {
    const before = rateAt(x.tarih), ch = F.find(f => f.tarih > x.tarih && f.tarih <= plus(x.tarih, 10));
    x.yayin = !!x.url || x.tarih < today;
    x.faiz = x.yayin ? (ch ? ch.oran : before) : null;
    x.bp = x.yayin && ok(before) && ok(x.faiz) ? Math.round((x.faiz - before) * 100) : null;
    x.karar = x.bp == null ? null : x.bp === 0 ? "Sabit" : `${x.bp > 0 ? "+" : "−"}${Math.abs(x.bp)}bp`;
    const d = new Date(x.tarih + "T00:00:00"), back = d.getDate() >= 4 ? 1 : 2, tm = new Date(d.getFullYear(), d.getMonth() - back, 1);
    x.tufeAy = `${tm.getFullYear()}-${String(tm.getMonth() + 1).padStart(2, "0")}`; x.tufe = PP_TUFE?.[x.tufeAy] ?? yoy(x.tufeAy);
    x.reel = ok(x.faiz) && ok(x.tufe) ? x.faiz - x.tufe : null; x.today = x.tarih === today;
  }
  return out;
}
function ppkSection(m) {
  const L = ppkList(m); if (!L.length) return `<div class="card empty">PPK verisi henüz yok.</div>`;
  const nowY = new Date().getFullYear(), years = [...new Set(L.map(x => +x.yil))].sort();
  // süreç tablosu: geçen yıl + bu yıl, bir sonraki toplantı dahil
  const nextI = L.findIndex(x => !x.yayin), win = L.filter((x, i) => +x.yil >= nowY - 1 && +x.yil <= nowY && (x.yayin || i === nextI));
  const pub = win.filter(x => x.yayin && ok(x.faiz)), before0 = pub.length ? (m.F.filter(f => f.tarih <= pub[0].tarih).pop() || {}).oran : null, endR = pub.length ? pub[pub.length - 1].faiz : null;
  const netBp = ok(before0) && ok(endR) ? Math.round((endR - before0) * 100) : null;
  const yrs = [...new Set(win.map(x => x.yil))];
  const table = `<article class="card ppk"><h3>${yrs.length > 1 ? `${yrs[0]}–${yrs[yrs.length - 1]}` : yrs[0] || ""} TCMB Politika Faizi Süreci</h3>
    <div class="tscroll"><table class="pptab"><thead><tr><th>PPK Tarihi</th><th>Karar</th><th class="num">Pol. Faizi</th><th class="num">TÜFE Yıllık</th><th class="num">Reel Getiri</th></tr></thead><tbody>`
    + [...win].reverse().map(x => `<tr class="${x.yayin ? "" : "next"}"><td>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${dShort(x.tarih)}</a>` : dShort(x.tarih)}${x.ara ? " *" : ""}${x.yayin ? "" : ' <span class="tag">Sıradaki</span>'}</td>
      <td class="${x.bp > 0 ? "up" : x.bp < 0 ? "down" : ""}">${x.karar || "—"}</td><td class="num">${ppPct(x.faiz, 2)}</td><td class="num">${ppPct(x.tufe, 2)}</td><td class="num ${cls(x.reel, 0.005)}">${ok(x.reel) ? `${sgnOf(x.reel, 1)}${nf(1).format(Math.abs(x.reel))} puan` : "—"}</td></tr>`).join("")
    + `</tbody></table></div><p class="ppnote">TÜFE Yıllık: PPK öncesi son açıklanan aya ait yıllık değişim (TÜİK). Reel getiri = Pol. Faizi − TÜFE Yıllık.${netBp != null ? ` Net ${netBp < 0 ? "indirim" : netBp > 0 ? "artış" : "değişim"}: ${Math.abs(netBp)}bp (%${nf(2).format(before0)}→%${nf(2).format(endR)}).` : ""} Kaynak: TCMB 1 Hafta Repo tarihçesi ve PPK kararları.${win.some(x => x.ara) ? " * Ara toplantı." : ""}</p></article>`;
  const Y = PPS.ppkYear && years.includes(PPS.ppkYear) ? PPS.ppkYear : (years.includes(nowY) ? nowY : years[years.length - 1]);
  const ys = L.filter(x => +x.yil === Y), yp = ys.filter(x => x.yayin && ok(x.faiz)), yb = yp.length ? (m.F.filter(f => f.tarih <= yp[0].tarih).pop() || {}).oran : null, ye = yp.length ? yp[yp.length - 1].faiz : null;
  const ybp = ok(yb) && ok(ye) ? Math.round((ye - yb) * 100) : null, today = new Date().toISOString().slice(0, 10);
  const cal = `<article class="card ppk ppcal" id="ppCal"><div class="ppcalh"><h3>PPK Takvimi</h3><select class="ppsel" id="ppYear" aria-label="Yıl">${years.map(y => `<option value="${y}"${y === Y ? " selected" : ""}>${y}</option>`).join("")}</select></div>
    <p class="ppsum">${yp.length ? `${yp.length} karar · yıl içinde ${ybp === 0 ? "değişiklik yok" : `${ybp < 0 ? "−" : "+"}${Math.abs(ybp)}bp`} (%${nf(2).format(yb)} → %${nf(2).format(ye)})` : "Bu yıl için henüz karar yok."}</p>
    <ol class="ppcl" title="Politika faizi grafiğini aç/kapat">${[...ys].reverse().map(x => { const st = x.today ? "today" : x.tarih < today ? "past" : "future";
      return `<li class="${st}"><span class="dot"></span><span class="dd">${dLabel(x.tarih)}${x.ara ? " *" : ""}${x.today ? ' <span class="tag">BUGÜN</span>' : ""}</span><span class="kk">${x.karar ? `${x.karar} → %${nf(2).format(x.faiz)}` : st === "future" ? "—" : ""}</span></li>`; }).join("")}</ol>
    <button type="button" class="more" id="ppkToggle">${PPS.ppkChart ? "Grafiği gizle" : "Politika faizi trendini göster (son 2 yıl)"}</button></article>`;
  return `<div class="ppkgrid">${table}${cal}</div>${PPS.ppkChart ? `<article class="card"><h3>Politika Faizi (1 Hafta Repo) — Son 2 Yıl</h3><div id="ppkChart"></div></article>` : ""}`;
}
function ppkDrawChart(m) {
  const el = $("#ppkChart"); if (!el) return;
  const end = new Date(), st = new Date(end); st.setFullYear(end.getFullYear() - 2);
  const s0 = st.toISOString().slice(0, 10), e0 = end.toISOString().slice(0, 10);
  const pts = []; let cur = m.rateAt(s0); pts.push([s0, cur, toTime(s0)]);
  for (const f of m.F) if (f.tarih > s0 && f.tarih <= e0) { const prev = new Date(f.tarih + "T00:00:00"); prev.setDate(prev.getDate() - 1); const pd = prev.toISOString().slice(0, 10); pts.push([pd, cur, toTime(pd)]); cur = f.oran; pts.push([f.tarih, cur, toTime(f.tarih)]); }
  pts.push([e0, cur, toTime(e0)]);
  lineChart(el, { series: [{ name: "Politika faizi (%)", color: PAL()[0], data: pts }], height: 280, yFmt: v => nf(2).format(v) });
}
function ppStep(pts) { const o = []; for (let k = 0; k < pts.length; k++) { if (k && ok(pts[k][1]) && ok(o[o.length - 1]?.[1]) && pts[k][1] !== o[o.length - 1][1]) o.push([pts[k][0], o[o.length - 1][1], pts[k][2] - 1]); o.push(pts[k]); } return o; }
function ppDefaultCharts(m) {
  const ids = ppClipIdx(m, PPS.drange), M = m.M, pal = PAL(), col = c => pal[(c - 1) % pal.length];
  const a = $("#ppAof"), n = $("#ppNet"); if (!a || !n) return;
  lineChart(a, { series: [
    { name: "TCMB AOF (%)", color: col(4), data: ppStep(ids.map(i => [m.dt[i], ok(M.aof[i]) ? M.aof[i] : null, toTime(m.dt[i])])) },
    { name: "Politika faizi (%)", color: col(1), dash: true, data: ppStep(ids.map(i => [m.dt[i], M.pol[i], toTime(m.dt[i])])) }], height: 240, yFmt: v => nf(1).format(v) });
  ppStackChart(n, { dates: ids.map(i => m.dt[i]), height: 240,
    stacks: [["fon", "Para piyasaları ile fonlama", 1], ["swap", "Swap fonlaması", 2], ["st_neg", "Sterilizasyon", 8]].map(([k, nm, c]) => ({ name: nm, color: col(c), vals: ids.map(i => ok(M[k][i]) ? M[k][i] / 1e3 : null) })),
    line: { name: "Swap dahil net fonlama", color: "var(--ink)", vals: ids.map(i => ok(M.nets[i]) ? M.nets[i] / 1e3 : null) } });
}
function ppRender() {
  const pane = $("#ppPane"); pane.classList.remove("hidden");
  $("#tBanks").closest(".bar").classList.add("hidden"); $(".tlayout").classList.add("hidden");
  const m = ppModel();
  if (!m) { pane.innerHTML = '<div class="card empty">Para politikası verisi henüz yok. Bir sonraki güncellemede gelecek.</div>'; return; }
  const sel = PPS.sel;
  pane.innerHTML = ppBoxes(m)
    + (sel ? `<article class="card ppchart"><div class="ppch"><h3>${esc((PP_PARTS[sel] || { title: "TCMB AOF ve Politika Faizi" }).title)} ${sel === "aof" ? "(%) — Günlük" : "(₺ mr) — Günlük"}</h3><div class="chips" id="ppRange"></div></div>
      <div class="pptiles">${ppPartTiles(m, sel)}</div><div id="ppChart"></div>
      <p class="ppnote">${dLabel(m.dt[m.last])} itibarıyla. ${sel === "swap" ? "Swap stokları (milyon USD) × TCMB USD/TRY alış kuru; alım yönlü − satım yönlü. Pozitif: TCMB swapla TL verdi, negatif: TL çekti." : sel === "aof" ? "Politika faizi: TCMB 1 hafta repo ihale faizi." : "Kaynak: TCMB EVDS, Açık Piyasa İşlemleri ile Fonlama ve Sterilizasyon."}</p></article>`
      : `<p class="ppnote">Kırılımı görmek için bir kutuya tıklayın.</p>`)
    + `<div class="ppdef"><div class="ppdefh"><span class="lbl">Dönem</span><div class="chips" id="ppDRange"></div></div><div class="ppkgrid2"><article class="card"><h3>TCMB AOF (%) — Günlük</h3><div id="ppAof"></div><p class="ppnote">Ağırlıklı ortalama fonlama maliyeti · kesikli: politika faizi</p></article>
      <article class="card"><h3>Net Fonlama (₺ mr) — Günlük</h3><div id="ppNet"></div><p class="ppnote">Para piyasaları ile fonlama + swap fonlaması − sterilizasyon</p></article></div></div>`
    + ppkSection(m);
  if (sel) { rangeChips($("#ppRange"), PPS.range, k => { PPS.range = k; ppDrawChart(m); }); ppDrawChart(m); }
  rangeChips($("#ppDRange"), PPS.drange, k => { PPS.drange = k; ppDefaultCharts(m); }); ppDefaultCharts(m);
  ppkDrawChart(m);
}
function ppHide() { const pane = $("#ppPane"); if (pane) pane.classList.add("hidden"); $("#tBanks").closest(".bar").classList.remove("hidden"); $(".tlayout").classList.remove("hidden"); }
function bindPp() {
  $("#ppPane").addEventListener("change", e => { if (e.target.id === "ppYear") { PPS.ppkYear = +e.target.value; ppRender(); } });
  $("#ppPane").addEventListener("click", e => {
    const b = e.target.closest("[data-pp]"); if (b) { PPS.sel = PPS.sel === b.dataset.pp ? null : b.dataset.pp; ppRender(); return; }
    if (e.target.closest("#ppkToggle") || e.target.closest(".ppcl")) { PPS.ppkChart = !PPS.ppkChart; ppRender(); if (PPS.ppkChart) $("#ppkChart")?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
  });
}
