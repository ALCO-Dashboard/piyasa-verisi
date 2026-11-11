const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1500, height: 1100 } });
  const err = []; p.on('pageerror', e => err.push(e.message));
  await p.goto('http://localhost:8768/tefas.html', { waitUntil: 'networkidle' }); await p.waitForTimeout(3000);
  await p.click('[data-ks="akim"]'); await p.waitForTimeout(2000);
  const bx = await (await p.$('#c-tr')).boundingBox(); await p.mouse.move(bx.x + bx.width * 0.8, bx.y + bx.height * 0.4); await p.waitForTimeout(600);
  await p.screenshot({ path: '../out/tip.png', clip: { x: bx.x, y: bx.y - 40, width: bx.width + 520, height: bx.height + 120 } });
  await p.selectOption('#f-cat', 'Hisse'); await p.waitForTimeout(100); await (await p.$('.dn')).screenshot({ path: '../out/dn100.png' });
  console.log(err.join('\n') || 'hata yok'); await b.close();
})();
