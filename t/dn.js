const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1500, height: 1100 } });
  const err = []; p.on('pageerror', e => err.push(e.message));
  await p.goto('http://localhost:8768/tefas.html', { waitUntil: 'networkidle' }); await p.waitForTimeout(2500);
  const st = async l => console.log(l, JSON.stringify(await p.evaluate(() => { const c = document.getElementById('c-dn'), ch = Chart.getChart(c), r = c.getBoundingClientRect(); return { w: r.width, h: r.height, cw: c.width, ch: c.height, dn: c.parentElement.getBoundingClientRect().height, data: ch ? ch.data.datasets[0].data.length : null }; })));
  await st('ilk');
  const steps = [['select', '#f-cat', 'Hisse'], ['select', '#f-cat', ''], ['click', '[data-ks="akim"]'], ['click', '#cc-tr button[data-c="Döviz"]'], ['select', '#f-kat', '1'], ['click', '#m-own'], ['click', '#m-tl'], ['fill', '#d1', '2026-10-15']];
  for (const [k, sel, v] of steps) { if (k === 'select') await p.selectOption(sel, v); else if (k === 'click') await p.click(sel); else { await p.fill(sel, v); await p.dispatchEvent(sel, 'change'); }
    await p.waitForTimeout(150); await st(k + ' ' + sel + ' +150ms'); await p.waitForTimeout(1500); await st(k + ' ' + sel + ' +1.6s'); }
  await (await p.$('#c-dn')).screenshot({ path: '../out/dn.png' }).catch(() => {});
  console.log(err.join('\n') || 'hata yok'); await b.close();
})();
