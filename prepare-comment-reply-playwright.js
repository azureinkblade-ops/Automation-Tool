const fs = require('fs');
const { chromium } = require('playwright');
const cdpUrl = "http://127.0.0.1:9222";
const platform = "meta";
const sourceUrl = "https://business.facebook.com/latest/inbox/all?mailbox_id=1099227976616388&selected_item_id=340282366841710301244276034609267626671&thread_type=IG_MESSAGE";
const snippet = "MoreMoreMore";
const reply = "Thank you for reading the story and taking the time to comment. I really appreciate the support!";
const outputPath = "C:\\Users\\David\\Documents\\Automation tool\\comment-reply-result.json";

function hostForPlatform(value) {
  return { youtube: 'studio.youtube.com', tiktok: 'tiktok.com', meta: 'business.facebook.com', x: 'x.com' }[value] || '';
}

(async () => {
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0] || await browser.newContext();
  const host = hostForPlatform(platform);
  let page = context.pages().find(candidate => {
    try { const h = new URL(candidate.url()).hostname.replace(/^www\./, ''); return h === host || h.endsWith('.' + host); } catch (_) { return false; }
  });
  if (!page) {
    page = await context.newPage();
    await page.goto(sourceUrl, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => null);
  }
  await page.bringToFront();
  await page.waitForLoadState('domcontentloaded', { timeout: 15000 }).catch(() => null);
  await page.waitForTimeout(1200);
  const textHit = page.getByText(snippet, { exact: false }).first();
  if (!(await textHit.count())) throw new Error('The selected comment is not visible on the current page. Open its comments page and retry.');
  await textHit.scrollIntoViewIfNeeded().catch(() => null);
  const container = textHit.locator('xpath=ancestor-or-self::*[self::article or @role="article" or self::ytcp-comment-thread or contains(@data-e2e,"comment")][1]');
  const scope = (await container.count()) ? container : textHit.locator('xpath=..');
  const replyButton = scope.getByRole('button', { name: /reply/i }).first();
  if (await replyButton.count()) await replyButton.click();
  else await textHit.click();
  await page.waitForTimeout(700);
  const editors = [
    page.locator('textarea[aria-label*="reply" i]:visible').last(),
    page.locator('[contenteditable="true"][aria-label*="reply" i]:visible').last(),
    page.locator('[contenteditable="true"]:visible').last(),
    page.locator('textarea:visible').last()
  ];
  let editor = null;
  for (const candidate of editors) { if (await candidate.count()) { editor = candidate; break; } }
  if (!editor) throw new Error('A reply editor did not open. The platform layout may have changed.');
  const tag = await editor.evaluate(node => node.tagName.toLowerCase());
  if (tag === 'textarea' || tag === 'input') await editor.fill(reply);
  else { await editor.click(); await page.keyboard.press('Control+A'); await page.keyboard.insertText(reply); }
  fs.writeFileSync(outputPath, JSON.stringify({ ok: true, platform, sourceUrl: page.url(), filled: true, submitted: false }, null, 2));
  process.exit(0);
})().catch(error => {
  fs.writeFileSync(outputPath, JSON.stringify({ ok: false, error: error.message, platform }, null, 2));
  process.exit(1);
});
