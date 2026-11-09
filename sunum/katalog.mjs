// Sunum kataloğunu üretir: sitenin tüm sekme ve alt sekmelerini gezip seçilebilir alanları (kart, grafik, tablo)
// ortak/sunum_katalog.json dosyasına yazar. Sunum sayfasındaki "Katalogdan ekle" bu listeyi gösterir.
// Kullanım (Playwright kurulu bir makinede, yayındaki ya da yerel site için):
//   node sunum/katalog.mjs https://alco-dashboard.github.io/piyasa-verisi/ ortak/sunum_katalog.json
// Site yapısı değişmedikçe yeniden üretmek gerekmez; yeni bir sekme ya da kart eklenince çalıştırılır.
import { chromium } from "playwright";
import fs from "node:fs";
const KOK = (process.argv[2] || "http://localhost:8765/").replace(/\/?$/, "/"), CIKTI = process.argv[3] || "ortak/sunum_katalog.json";
const SAYFALAR = [
  ["ozet/", null], ["makro/", null], ["bankacilik/", null],
  ["tcmb/", "Bankacılık Verileri › TCMB › Rezervler"], ["zk/", "Bankacılık Verileri › TCMB › Zorunlu Karşılık"],
  ["katilim/", "Bankacılık Verileri › Katılım Bülteni"], ["bilanco/", null], ["tefas.html", null]];
const SEKME = /^(tabs|tSub|mkTabs|psTabs|sTabs|gTabs|sekme|menu|bFreq)$/;
const ATLA = { "bankacilik/": /Rezervler|Zorunlu Karşılık|Katılım Bülteni/ };     // iç iframe'ler kendi sayfalarından taranır
const b = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
const alanlar = [], gorulen = new Set();
const bekle = ms => new Promise(r => setTimeout(r, ms));
async function topla(sayfa, onEk) {
  const L = await p.evaluate(([onEk]) => {
    const A = window.alcoSunum; if (!A) return [];
    const SEC = ".card,.kc,.tkp,.yan,.box,.panel,aside,article,.chartbox";
    const el = [...document.querySelectorAll(SEC)].filter(e => { const r = e.getBoundingClientRect(); return e.offsetParent && r.width >= 200 && r.height >= 90 && !e.closest("#alcoTop,.ss-ui"); });
    const ust = el.filter(e => !el.some(x => x !== e && x.contains(e) && !x.matches(".kc")));   // iç içe olanlardan dıştakini al
    return ust.map(e => { const o = A.ogeYap(e); if (onEk) o.yolAd = onEk + o.yolAd.split(" › ").slice(1).map(x => " › " + x).join(""); delete o.id; delete o.t; return o; })
      .filter(o => o.ad && o.ad.length > 1 && o.ad !== "Alan" && !/^[＋+]/.test(o.ad));
  }, [onEk]);
  for (const o of L) { const k = o.sayfa + "|" + o.yolAd + "|" + o.konum.n + "|" + o.konum.i; if (!gorulen.has(k)) { gorulen.add(k); alanlar.push(o); } }
}
async function gez(sayfa, onEk, yol, derinlik) {
  await topla(sayfa, onEk);
  if (derinlik > 2) return;
  const gruplar = await p.evaluate(([yol, kaynak]) => {
    const re = new RegExp(kaynak);
    return [...new Set([...document.querySelectorAll("button[aria-pressed],button[aria-selected],[role=tab]")].filter(b => b.offsetParent)
      .map(b => b.parentElement?.closest("[id]")?.id).filter(id => id && re.test(id) && !yol.includes(id)))];
  }, [yol, SEKME.source]);
  if (!gruplar.length) return;
  const g = gruplar[0];
  const n = await p.evaluate(g => document.getElementById(g).querySelectorAll("button[aria-pressed],button[aria-selected],[role=tab]").length, g);
  for (let i = 0; i < n; i++) {
    const ad = await p.evaluate(([g, i]) => { const b = document.getElementById(g).querySelectorAll("button[aria-pressed],button[aria-selected],[role=tab]")[i]; if (!b || !b.offsetParent) return null; b.click(); return b.textContent.trim(); }, [g, i]);
    if (!ad || (ATLA[sayfa] && ATLA[sayfa].test(ad))) continue;
    await bekle(1800);
    await gez(sayfa, onEk, [...yol, g], derinlik + 1);
  }
}
for (const [sayfa, onEk] of SAYFALAR) {
  await p.goto(KOK + sayfa, { waitUntil: "load" }); await bekle(4000);
  const once = alanlar.length;
  await gez(sayfa, onEk, [], 0);
  console.log(sayfa, alanlar.length - once, "alan");
}
await b.close();
fs.writeFileSync(CIKTI, JSON.stringify({ alanlar }));
console.log("toplam", alanlar.length, "→", CIKTI);
