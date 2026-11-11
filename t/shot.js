const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1500, height: 1100 } });
  const err = []; p.on('pageerror', e => err.push(e.message)); p.on('console', m => { if (m.type() === 'error') err.push(m.text()); });
  await p.goto('http://localhost:8768/tefas.html', { waitUntil: 'networkidle' }); await p.waitForTimeout(2500);
  for (const a of process.argv.slice(3)) { if (a.startsWith('fill:')) { const [sel, v] = a.slice(5).split('='); if (sel === '#ps') await p.selectOption(sel, v); else { await p.fill(sel, v); await p.dispatchEvent(sel, 'change'); } } else await p.click(a); await p.waitForTimeout(1500); }
  await p.waitForTimeout(1500);
  const t = await p.evaluate(() => ({ kpi: document.querySelector('[data-ks="akim"] .v')?.textContent, wk: document.getElementById('wk-t').textContent, rows: document.querySelectorAll('#tb tr').length, dd: document.getElementById('dd-t').textContent }));
  console.log(JSON.stringify(t));
  await p.screenshot({ path: process.argv[2], fullPage: true }); console.log(err.join('\n') || 'hata yok'); await b.close();
})();
