const fs = require('fs');
const { chromium } = require('playwright');

const cdpUrl = "http://127.0.0.1:9222";
const resultPath = "C:\\Users\\David\\Documents\\Automation tool\\youtube-comment-pin-results.json";
const apiBases = ['http://127.0.0.1:8765', 'http://localhost:8765', 'http://127.0.0.1:8765', 'http://localhost:8765', 'http://127.0.0.1:8766', 'http://localhost:8766'];
let activeBase = '';
const results = [];

function wait(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
function cleanText(value) { return String(value || '').replace(/\s+/g, ' ').trim(); }
function visible(el) {
  if (!el) return false;
  const box = el.getBoundingClientRect();
  const style = window.getComputedStyle(el);
  return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
}
async function api(path, options = {}) {
  const bases = activeBase ? [activeBase, ...apiBases.filter((base) => base !== activeBase)] : apiBases;
  let lastError = null;
  for (const base of bases) {
    try {
      const response = await fetch(`${base}${path}`, { cache: 'no-store', ...options });
      if (response.ok) {
        activeBase = base;
        return await response.json();
      }
      lastError = new Error(`Automation tool at ${base} returned ${response.status}: ${await response.text()}`);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error('Automation tool is not reachable.');
}
async function ack(item, status, error = '') {
  return api('/api/youtube-comment-helper/ack', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({commentId: item.id, status, error})
  });
}
async function pending(videoId = '') {
  const suffix = videoId ? `?videoId=${encodeURIComponent(videoId)}` : '';
  return api(`/api/youtube-comment-helper/pending${suffix}`);
}
async function getText(page, locator) {
  try { return cleanText(await locator.innerText({ timeout: 1500 })); } catch (_) { return ''; }
}
async function existingMatchingComment(page, item) {
  const needle = cleanText(item.comment).slice(0, 70).toLowerCase();
  if (!needle) return null;
  const threads = page.locator('ytd-comment-thread-renderer');
  const count = await threads.count().catch(() => 0);
  for (let i = 0; i < count; i += 1) {
    const thread = threads.nth(i);
    const text = (await getText(page, thread)).toLowerCase();
    if (text.includes(needle)) return thread;
  }
  return null;
}
async function scrollToComments(page) {
  for (let attempt = 0; attempt < 18; attempt += 1) {
    const comments = page.locator('ytd-comments').first();
    if (await comments.count().catch(() => 0)) {
      await comments.scrollIntoViewIfNeeded().catch(() => null);
      await page.waitForTimeout(900);
      if (await page.locator('#placeholder-area, #simplebox-placeholder, #contenteditable-root[contenteditable="true"]').count().catch(() => 0)) return;
    }
    await page.mouse.wheel(0, 900);
    await page.waitForTimeout(700);
  }
}
async function findCommentEditor(page) {
  await scrollToComments(page);
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const placeholder = page.locator('#placeholder-area:visible, #simplebox-placeholder:visible, ytd-comment-simplebox-renderer').first();
    if (await placeholder.count().catch(() => 0)) {
      await placeholder.click({ timeout: 3000 }).catch(() => null);
      await page.waitForTimeout(500);
    }
    const editor = page.locator('ytd-comment-simplebox-renderer #contenteditable-root[contenteditable="true"]:visible, #contenteditable-root[contenteditable="true"]:visible').first();
    if (await editor.count().catch(() => 0)) return editor;
    await page.keyboard.press('PageDown').catch(() => null);
    await page.waitForTimeout(700);
  }
  return null;
}
async function postComment(page, item) {
  if (await existingMatchingComment(page, item)) {
    await ack(item, 'posted');
    return true;
  }
  const editor = await findCommentEditor(page);
  if (!editor) throw new Error('YouTube comment box was not available. The video may not be public, or comments may be disabled.');
  await editor.click({ timeout: 5000 });
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A').catch(() => null);
  await page.keyboard.type(item.comment || '', { delay: 1 });
  await page.waitForTimeout(700);
  const submit = page.locator('ytd-comment-simplebox-renderer #submit-button button:not([disabled]), ytd-comment-simplebox-renderer #submit-button:not([disabled]), button[aria-label*="Comment"]:not([disabled])').first();
  await submit.waitFor({ state: 'visible', timeout: 10000 });
  await submit.click({ timeout: 5000 });
  for (let attempt = 0; attempt < 20; attempt += 1) {
    await page.waitForTimeout(1000);
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => null);
    await scrollToComments(page);
    if (await existingMatchingComment(page, item)) {
      await ack(item, 'posted');
      return true;
    }
  }
  await ack(item, 'posted', 'Comment submitted, but it was not visible yet for pinning.');
  return true;
}
async function pinComment(page, item) {
  for (let attempt = 0; attempt < 24; attempt += 1) {
    await scrollToComments(page);
    const thread = await existingMatchingComment(page, item);
    if (thread) {
      const text = await getText(page, thread);
      if (/pinned by/i.test(text)) return true;
      await thread.hover().catch(() => null);
      const menu = thread.locator('#action-menu button:visible, #action-menu [role="button"]:visible, yt-icon-button button:visible').first();
      if (await menu.count().catch(() => 0)) {
        await menu.click({ timeout: 5000 }).catch(() => null);
        await page.waitForTimeout(700);
        const pin = page.locator('ytd-menu-service-item-renderer:visible, tp-yt-paper-item:visible, [role="menuitem"]:visible').filter({ hasText: /^\s*Pin\b/i }).first();
        if (await pin.count().catch(() => 0)) {
          await pin.click({ timeout: 5000 });
          await page.waitForTimeout(700);
          const confirm = page.locator('yt-confirm-dialog-renderer button:visible, tp-yt-paper-dialog button:visible').filter({ hasText: /^\s*Pin\s*$/i }).first();
          if (await confirm.count().catch(() => 0)) await confirm.click({ timeout: 5000 });
          await page.waitForTimeout(1500);
          return true;
        }
      }
    }
    await page.mouse.wheel(0, 700);
    await page.waitForTimeout(1000);
  }
  if (await existingMatchingComment(page, item)) throw new Error('The posted comment is visible, but the pin menu was not available.');
  throw new Error('The posted comment was not found for pinning.');
}

(async () => {
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0] || await browser.newContext();
  let page = context.pages().find((candidate) => {
    try { return new URL(candidate.url()).hostname.endsWith('youtube.com'); } catch (_) { return false; }
  });
  if (!page) page = await context.newPage();
  for (let index = 0; index < 80; index += 1) {
    const data = await pending();
    const item = data.item;
    if (!item || !item.watchUrl) break;
    try {
      await page.goto(item.watchUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.bringToFront().catch(() => null);
      await page.waitForTimeout(2500);
      if (item.status !== 'posted') await postComment(page, item);
      await pinComment(page, item);
      await ack(item, 'pinned');
      results.push({ id: item.id, title: item.title, videoId: item.videoId, status: 'pinned' });
    } catch (error) {
      const failedStatus = /visible, but the pin menu|not visible yet/i.test(error.message) ? 'posted' : 'failed';
      await ack(item, failedStatus, error.message).catch(() => null);
      results.push({ id: item.id, title: item.title, videoId: item.videoId, status: failedStatus, error: error.message });
    }
    fs.writeFileSync(resultPath, JSON.stringify({ updatedAt: new Date().toISOString(), results }, null, 2), 'utf8');
    await page.waitForTimeout(800);
  }
  fs.writeFileSync(resultPath, JSON.stringify({ finishedAt: new Date().toISOString(), results }, null, 2), 'utf8');
  process.exit(0);
})().catch((error) => {
  fs.writeFileSync(resultPath, JSON.stringify({ finishedAt: new Date().toISOString(), error: error.message, stack: error.stack, results }, null, 2), 'utf8');
  process.exit(1);
});
