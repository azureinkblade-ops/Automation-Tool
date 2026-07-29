const fs = require('fs');
const { chromium } = require('playwright');

const cdpUrl = "http://127.0.0.1:9222";
const targets = [{"platform": "tiktok", "target": "thekennygould", "label": "thekennygould", "url": "https://www.tiktok.com/@thekennygould"}, {"platform": "tiktok", "target": "eddiequinnlemon_", "label": "eddiequinnlemon_", "url": "https://www.tiktok.com/@eddiequinnlemon_"}, {"platform": "facebook", "target": "The.open.minded.guides", "label": "The.open.minded.guides", "url": "https://www.facebook.com/The.open.minded.guides"}, {"platform": "instagram", "target": "njs_reads", "label": "njs_reads", "url": "https://www.instagram.com/njs_reads/"}, {"platform": "tiktok", "target": "authorlogankarlie", "label": "authorlogankarlie", "url": "https://www.tiktok.com/@authorlogankarlie"}];
const outputPath = "C:\\Users\\David\\Documents\\Automation tool\\creator-benchmarks-playwright-results.json";
const maxPerSource = 6;

function compactNumber(value) {
  if (!value) return 0;
  const text = String(value).replace(/,/g, '').trim();
  const match = text.match(/(\d+(?:\.\d+)?)([kKmM])?/);
  if (!match) return 0;
  let n = Number(match[1] || 0);
  if ((match[2] || '').toLowerCase() === 'k') n *= 1000;
  if ((match[2] || '').toLowerCase() === 'm') n *= 1000000;
  return n;
}

function parseMetrics(text) {
  const metrics = {};
  const normalized = String(text || '').replace(/\s+/g, ' ');
  const pairs = [
    ['followers', /(followers|follower)\D{0,25}(\d[\d,.]*[kKmM]?)/i],
    ['likes', /(likes|like)\D{0,25}(\d[\d,.]*[kKmM]?)/i],
    ['views', /(views|plays|reels views)\D{0,25}(\d[\d,.]*[kKmM]?)/i],
    ['comments', /(comments|replies)\D{0,25}(\d[\d,.]*[kKmM]?)/i],
    ['shares', /(shares)\D{0,25}(\d[\d,.]*[kKmM]?)/i]
  ];
  for (const [key, pattern] of pairs) {
    const found = normalized.match(pattern);
    if (found) metrics[key] = compactNumber(found[2]);
  }
  return metrics;
}

async function visibleText(page) {
  await page.waitForLoadState('domcontentloaded', { timeout: 20000 }).catch(() => null);
  await page.waitForTimeout(2500);
  for (let i = 0; i < 3; i++) {
    await page.mouse.wheel(0, 1200).catch(() => null);
    await page.waitForTimeout(1200);
  }
  return await page.evaluate(() => document.body ? document.body.innerText : '').catch(() => '');
}

async function collectCards(page, platform) {
  return await page.evaluate((platform) => {
    const anchors = Array.from(document.querySelectorAll('a[href]'));
    const rows = [];
    const seen = new Set();
    for (const a of anchors) {
      const href = a.href || '';
      const text = (a.innerText || a.getAttribute('aria-label') || a.title || '').replace(/\s+/g, ' ').trim();
      const isPost =
        (platform === 'tiktok' && /\/video\//.test(href)) ||
        (platform === 'instagram' && /\/(p|reel)\//.test(href)) ||
        (platform === 'facebook' && /(posts|videos|reel|watch)/.test(href));
      if (!isPost || seen.has(href)) continue;
      seen.add(href);
      const parentText = (a.closest('article, div')?.innerText || text || '').replace(/\s+/g, ' ').trim();
      rows.push({ url: href, title: text || parentText.slice(0, 180), textSample: parentText.slice(0, 2000) });
      if (rows.length >= 12) break;
    }
    return rows;
  }, platform).catch(() => []);
}

(async () => {
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0] || await browser.newContext();
  const results = [];
  for (const target of targets) {
    const page = await context.newPage();
    await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => null);
    const text = await visibleText(page);
    const profileMetrics = parseMetrics(text);
    const cards = await collectCards(page, target.platform);
    if (!cards.length) {
      results.push({
        platform: target.platform,
        target: target.target,
        creator: target.label,
        url: page.url(),
        title: target.label,
        textSample: text.slice(0, 2500),
        metrics: profileMetrics,
        source: 'browser_profile',
        confidence: 'low_public_browser',
        gatheredAt: new Date().toISOString()
      });
    }
    for (const card of cards.slice(0, maxPerSource)) {
      results.push({
        platform: target.platform,
        target: target.target,
        creator: target.label,
        url: card.url,
        title: card.title,
        textSample: card.textSample,
        metrics: Object.assign({}, profileMetrics, parseMetrics(card.textSample)),
        source: 'browser_post_grid',
        confidence: 'medium_public_browser',
        gatheredAt: new Date().toISOString()
      });
    }
    await page.close().catch(() => null);
  }
  fs.writeFileSync(outputPath, JSON.stringify({ gatheredAt: new Date().toISOString(), results }, null, 2), 'utf8');
  process.exit(0);
})().catch(error => {
  fs.writeFileSync(outputPath, JSON.stringify({ gatheredAt: new Date().toISOString(), error: error.message, stack: error.stack }, null, 2), 'utf8');
  process.exit(1);
});
