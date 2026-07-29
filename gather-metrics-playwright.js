const fs = require('fs');
const { chromium } = require('playwright');

const cdpUrl = "http://127.0.0.1:9222";
const targets = [{"platform": "youtube", "url": "https://studio.youtube.com/channel/UC/analytics/tab-overview/period-default", "pathHints": ["analytics"]}, {"platform": "tiktok", "url": "https://www.tiktok.com/analytics", "pathHints": ["analytics"]}, {"platform": "instagram", "url": "https://business.facebook.com/latest/insights", "pathHints": ["insights"]}, {"platform": "facebook", "url": "https://business.facebook.com/latest/insights", "pathHints": ["insights"]}, {"platform": "x", "url": "https://analytics.x.com", "pathHints": []}, {"platform": "patreon", "url": "https://www.patreon.com/insights", "pathHints": ["insights"]}, {"platform": "royalroad", "url": "https://www.royalroad.com/author-dashboard", "pathHints": ["author-dashboard"]}];
const outputPath = "C:\\Users\\David\\Documents\\Automation tool\\runtime\\jobs\\metrics-gather-results.json";
const openMissing = true;

async function pageText(page) {
  try {
    await page.waitForLoadState('domcontentloaded', { timeout: 15000 }).catch(() => null);
    await page.waitForTimeout(2500);
    return await page.evaluate(() => document.body ? document.body.innerText : '');
  } catch (error) {
    return '';
  }
}

(async () => {
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0] || await browser.newContext();
  const results = [];
  for (const target of targets) {
    let page = context.pages().find(p => {
      try {
        const parsed = new URL(p.url());
        const host = parsed.hostname.replace(/^www\\./, '');
        const targetHost = new URL(target.url).hostname.replace(/^www\\./, '');
        const hostMatches = host === targetHost || host.endsWith('.' + targetHost);
        const hints = target.pathHints || [];
        return hostMatches && (!hints.length || hints.some(hint => parsed.pathname.toLowerCase().includes(hint)));
      } catch (_) {
        return false;
      }
    });
    let opened = false;
    if (!page) {
      if (!openMissing) {
        results.push({ platform: target.platform, targetUrl: target.url, skipped: true, reason: 'No existing logged-in tab', gatheredAt: new Date().toISOString() });
        continue;
      }
      page = await context.newPage();
      opened = true;
      await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => null);
    } else {
      await page.bringToFront().catch(() => null);
    }
    const text = await pageText(page);
    results.push({
      platform: target.platform,
      url: page.url(),
      targetUrl: target.url,
      opened,
      textSample: text.slice(0, 12000),
      textLength: text.length,
      gatheredAt: new Date().toISOString()
    });
  }
  fs.writeFileSync(outputPath, JSON.stringify({
    gatheredAt: new Date().toISOString(),
    cdpUrl,
    results
  }, null, 2), 'utf8');
  process.exit(0);
})().catch(error => {
  fs.writeFileSync(outputPath, JSON.stringify({
    gatheredAt: new Date().toISOString(),
    error: error.message,
    stack: error.stack
  }, null, 2), 'utf8');
  process.exit(1);
});
