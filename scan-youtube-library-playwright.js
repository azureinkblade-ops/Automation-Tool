const fs = require('fs');
const { chromium } = require('playwright');

const cdpUrl = "http://127.0.0.1:9222";
const outputPath = "C:\\Users\\David\\Documents\\Automation tool\\runtime\\cache\\youtube-library-scan.json";
const configuredChannelId = "UCBKiJENwFqvVIItR4WbMY6A";
const verifiedPinnedIds = new Set(["-4OOcuYNesY", "-8MpZrOIsII", "-swqQ6GZ15o", "BnNfizLwNqk", "Eg4NdOvhPiM", "GsWYX1P1610", "HTPIEM_XQ0M", "KLcb2moSyZI", "L89VbNwmpNc", "NIo6eoTQpoo", "OyCR_NqpVh4", "PB9aFxyvNC4", "PQIAXi5t20A", "PxcDroMxLW8", "Qo0bFM6U9GA", "RoCjPdO3IMA", "S0TmNnaLyqs", "VBV32jrf9tc", "VCexnM6peds", "VKuiRHVpjf0", "XG4UmpYAALk", "YlNdJm8v2p0", "aZUIDJDYCl8", "atq85Ju-OsE", "bt0HanyzzxE", "cfEsNx5qBs0", "dZHKOncXlJ8", "h7kP0B3ZBsE", "iQXnoGSDP08", "kM35GT8gox4", "kiSV6T9Y8S8", "kxQMwtllPb4", "lL-AfFnMKGo", "nHOUWdDPqBs", "p9meC6Bdj-M", "pqdj3mugMNo", "qc7cByXLC4w", "s0OPriLwtX8", "wf7RIKo_PMI"]);

function durationSeconds(value) {
  const match = String(value || '').match(/(?:^|\s)(\d{1,2}:)?(\d{1,2}):(\d{2})(?:\s|$)/);
  if (!match) return 0;
  const parts = match[0].trim().split(':').map(Number);
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return parts[0] * 60 + parts[1];
}

function normalizeVideoRows(rows) {
  return rows.map((row) => {
    const titleElement = row.querySelector('a#video-title, #video-title');
    const linkElement = titleElement || row.querySelector('a[href*="/video/"]');
    const title = String(titleElement?.getAttribute('aria-label') || titleElement?.getAttribute('title') || titleElement?.textContent || '').trim();
    const href = String(linkElement?.href || linkElement?.getAttribute('href') || '');
    const idMatch = href.match(/\/video\/([A-Za-z0-9_-]{11})/);
    const text = String(row.innerText || row.textContent || '').replace(/\s+/g, ' ').trim();
    return { title, videoId: idMatch ? idMatch[1] : '', editUrl: href, text };
  }).filter((video) => video.title && video.videoId);
}

async function collectVisibleRows(page, byId) {
  const rows = await page.locator('ytcp-video-row').evaluateAll(normalizeVideoRows).catch(() => []);
  for (const row of rows) byId.set(row.videoId, row);
  return rows.length;
}

async function scrollStudioVideoTable(page) {
  await page.evaluate(() => {
    const candidates = [
      document.querySelector('ytcp-app'),
      document.querySelector('#main'),
      document.querySelector('#scroll-container'),
      document.querySelector('ytcp-video-section'),
      document.scrollingElement,
      document.documentElement,
      document.body
    ].filter(Boolean);
    for (const element of candidates) {
      try {
        const step = Math.max(900, Math.floor((element.clientHeight || window.innerHeight || 900) * 1.35));
        element.scrollTop = Math.min(element.scrollHeight || element.scrollTop + step, (element.scrollTop || 0) + step);
      } catch (_) {}
    }
  }).catch(() => null);
  await page.mouse.wheel(0, 1400).catch(() => null);
}

(async () => {
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0] || await browser.newContext();
  let page = context.pages().find((candidate) => {
    try { return new URL(candidate.url()).hostname === 'studio.youtube.com'; } catch (_) { return false; }
  });
  if (!page) {
    page = await context.newPage();
    await page.goto('https://studio.youtube.com', { waitUntil: 'domcontentloaded', timeout: 60000 });
  }
  await page.bringToFront().catch(() => null);
  await page.waitForTimeout(2500);
  const channelMatch = page.url().match(/\/channel\/([^/]+)/);
  const channelId = channelMatch ? channelMatch[1] : configuredChannelId;
  if (channelId) {
    await page.goto(`https://studio.youtube.com/channel/${channelId}/videos/upload`, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => null);
  } else {
    const content = page.getByText('Content', { exact: true }).first();
    if (await content.count()) await content.click().catch(() => null);
  }
  await page.waitForTimeout(3500);
  const videosTab = page.getByText('Videos', { exact: true }).first();
  if (await videosTab.count()) await videosTab.click().catch(() => null);
  await page.waitForTimeout(2500);

  const byId = new Map();
  let stablePasses = 0;
  let previousTotal = 0;
  for (let pass = 0; pass < 90 && stablePasses < 8; pass += 1) {
    await collectVisibleRows(page, byId);
    stablePasses = byId.size === previousTotal ? stablePasses + 1 : 0;
    previousTotal = byId.size;
    await scrollStudioVideoTable(page);
    await page.waitForTimeout(800);
  }

  const videos = Array.from(byId.values());
  const skippedVerifiedPinned = videos
    .filter((video) => verifiedPinnedIds.has(video.videoId))
    .map((video) => ({ ...video, reason: 'Pinned comment already verified.' }));
  const normalized = videos
    .filter((video) => video.title && video.videoId)
    .map((video) => ({
      ...video,
      duration: durationSeconds(video.text),
      visibility: /\bpublic\b/i.test(video.text) ? 'public' : (/\bscheduled\b/i.test(video.text) ? 'scheduled' : (/\bprivate\b/i.test(video.text) ? 'private' : 'unknown')),
      madeForKids: /\bmade for kids\b/i.test(video.text),
      watchUrl: `https://www.youtube.com/watch?v=${video.videoId}`
    }));
  fs.writeFileSync(outputPath, JSON.stringify({ scannedAt: new Date().toISOString(), studioUrl: page.url(), videos: normalized, skippedVerifiedPinned }, null, 2), 'utf8');
  process.exit(0);
})().catch((error) => {
  fs.writeFileSync(outputPath, JSON.stringify({ scannedAt: new Date().toISOString(), error: error.message, stack: error.stack, videos: [] }, null, 2), 'utf8');
  process.exit(1);
});
