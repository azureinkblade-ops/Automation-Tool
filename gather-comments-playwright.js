const fs = require('fs');
const { chromium } = require('playwright');
const cdpUrl = "http://127.0.0.1:9222";
const targets = [{"platform": "youtube", "itemType": "comment", "label": "YouTube comments", "url": "https://studio.youtube.com/channel/UC/comments/inbox", "pathHints": ["comments"], "selectors": ["ytcp-comment-thread #content-text", "ytcp-comment-thread"]}, {"platform": "tiktok", "itemType": "mixed", "label": "TikTok inbox", "url": "https://www.tiktok.com/inbox", "pathHints": ["inbox"], "selectors": ["[data-e2e*='comment']", "[data-e2e*='inbox'] [role='button']"]}, {"platform": "meta", "itemType": "mixed", "label": "Facebook and Instagram inbox", "url": "https://business.facebook.com/latest/inbox/all", "pathHints": ["inbox"], "selectors": ["[role='article']", "[data-pagelet*='Inbox'] [role='button']"]}, {"platform": "x", "itemType": "comment", "label": "X mentions", "url": "https://x.com/notifications/mentions", "pathHints": ["notifications", "mentions"], "selectors": ["article[data-testid='tweet']", "[data-testid='tweetText']"]}, {"platform": "x", "itemType": "message", "label": "X messages", "url": "https://x.com/messages", "pathHints": ["messages", "i/chat"], "selectors": ["[data-testid='conversation']", "[data-testid='conversationItem']", "[data-testid='messageEntry']", "[data-testid='messageText']", "[role='main'] [role='link']"]}, {"platform": "patreon", "itemType": "message", "label": "Patreon messages", "url": "https://www.patreon.com/messages", "pathHints": ["messages"], "selectors": ["[data-tag='message-thread']", "[role='main'] [role='button']", "[role='main'] [role='link']"]}, {"platform": "royalroad", "itemType": "message", "label": "Royal Road messages", "url": "https://www.royalroad.com/my/messages", "pathHints": ["messages"], "selectors": [".mail-item", ".message-item", "main a[href*='/message']", "main a[href*='/messages']"]}];
const outputPath = "C:\\Users\\David\\Documents\\Automation tool\\runtime\\jobs\\comment-gather-results.json";
const openMissing = false;

async function findPage(context, target) {
  const pages = context.pages();
  const targetHost = new URL(target.url).hostname.replace(/^www\./, '');
  let page = pages.find(candidate => {
    try {
      const parsed = new URL(candidate.url());
      const host = parsed.hostname.replace(/^www\./, '');
      return (host === targetHost || host.endsWith('.' + targetHost)) && target.pathHints.some(hint => parsed.pathname.toLowerCase().includes(hint));
    } catch (_) { return false; }
  });
  if (!page && target.platform === 'x' && target.itemType === 'message') {
    page = pages.find(candidate => {
      try {
        const parsed = new URL(candidate.url());
        const host = parsed.hostname.replace(/^www\./, '');
        return host === targetHost || host.endsWith('.' + targetHost);
      } catch (_) { return false; }
    });
  }
  if (!page && openMissing) {
    page = await context.newPage();
    await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => null);
  }
  if (page) {
    try {
      const parsed = new URL(page.url());
      const host = parsed.hostname.replace(/^www\./, '');
      const path = parsed.pathname.toLowerCase();
      const onTarget = (host === targetHost || host.endsWith('.' + targetHost)) && target.pathHints.some(hint => path.includes(hint));
      if (!onTarget && (openMissing || (target.platform === 'x' && target.itemType === 'message'))) await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => null);
    } catch (_) {}
  }
  return page;
}

async function collectGenericCandidates(page, selectors) {
  return await page.evaluate((selectors) => {
    const seen = new Set();
    const rows = [];
    for (const selector of selectors) {
      for (const node of document.querySelectorAll(selector)) {
        const contentNode = node.querySelector('[data-testid="tweetText"], #content-text') || node;
        const text = (contentNode.innerText || contentNode.textContent || '').replace(/\s+/g, ' ').trim();
        if (text.length < 3 || text.length > 1800 || seen.has(text)) continue;
        seen.add(text);
        const authorNode = node.querySelector('[data-testid="User-Name"], #author-text, [data-e2e*="user"], a[role="link"]');
        rows.push({ text, author: (authorNode?.innerText || authorNode?.textContent || '').replace(/\s+/g, ' ').trim(), matchedSelector: selector });
        if (rows.length >= 60) break;
      }
      if (rows.length >= 60) break;
    }
    return rows;
  }, selectors).catch(() => []);
}

async function collectXMessageCandidates(page) {
  const rows = [];
  const seen = new Set();
  const readVisibleMessages = async (authorLabel, selectorName) => {
    const messages = await page.evaluate(() => {
      const blocked = new Set([
        'messages', 'new message', 'search direct messages', 'settings', 'requests',
        'compose message', 'send', 'add emoji', 'add photo', 'start a new message',
        'you don’t have any messages', 'you do not have any messages'
      ]);
      const nodes = [
        ...document.querySelectorAll('[data-testid="messageEntry"]'),
        ...document.querySelectorAll('[data-testid="messageText"]'),
        ...document.querySelectorAll('[data-testid="cellInnerDiv"] div[dir="auto"]'),
        ...document.querySelectorAll('[role="main"] div[dir="auto"]'),
        ...document.querySelectorAll('[role="main"] span')
      ];
      const values = [];
      const seenText = new Set();
      for (const node of nodes) {
        const text = (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
        const lowered = text.toLowerCase();
        if (text.length < 3 || text.length > 1800 || blocked.has(lowered) || seenText.has(text)) continue;
        if (/^(home|explore|notifications|grok|premium|profile|more|post)$/.test(lowered)) continue;
        if (/^\d{1,2}:\d{2}\s*(am|pm)?$/i.test(text)) continue;
        const isMessageNode = Boolean(node.closest('[data-testid="messageEntry"], [data-testid="messageText"]'));
        if (!isMessageNode && !/[?.!,]/.test(text) && text.split(/\s+/).length <= 3) continue;
        seenText.add(text);
        values.push(text);
        if (values.length >= 40) break;
      }
      return values;
    }).catch(() => []);
    for (const text of messages) {
      const key = `${authorLabel}|${text}`;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push({ text, author: authorLabel, matchedSelector: selectorName });
      if (rows.length >= 60) return true;
    }
    return false;
  };
  const currentPath = (() => {
    try { return new URL(page.url()).pathname.toLowerCase(); } catch (_) { return ''; }
  })();
  if (currentPath.includes('/i/chat') || currentPath.includes('/messages/')) {
    await page.waitForTimeout(2500);
    await readVisibleMessages('Current X conversation', 'x-current-message-thread');
    if (rows.length) return rows;
  }
  await page.goto('https://x.com/messages', { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => null);
  await page.waitForTimeout(4500);
  const threadSelectors = [
    'a[href*="/messages/"][role="link"]',
    'a[href*="/i/chat/"][role="link"]',
    '[data-testid="conversation"]',
    '[data-testid="conversationItem"]',
    '[role="main"] a[href*="/messages/"]',
    '[role="main"] a[href*="/i/chat/"]',
    '[role="main"] [role="button"]'
  ];
  let threads = page.locator(threadSelectors.join(', '));
  let count = Math.min(await threads.count().catch(() => 0), 12);
  if (!count) {
    await readVisibleMessages('X messages', 'x-messages-visible-fallback');
    if (rows.length) return rows;
    const fallback = await collectGenericCandidates(page, ['[data-testid="cellInnerDiv"]', '[role="main"] [role="link"]', '[role="main"] [role="button"]']);
    return fallback.map(item => ({ ...item, matchedSelector: item.matchedSelector || 'x-messages-list-fallback' }));
  }
  for (let index = 0; index < count; index += 1) {
    threads = page.locator(threadSelectors.join(', '));
    const thread = threads.nth(index);
    const label = (await thread.innerText({ timeout: 1500 }).catch(() => '')).replace(/\s+/g, ' ').trim();
    await thread.click({ timeout: 5000 }).catch(() => null);
    await page.waitForTimeout(1800);
    if (await readVisibleMessages(label || 'X conversation', 'x-message-thread')) return rows;
    await page.goto('https://x.com/messages', { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => null);
    await page.waitForTimeout(1200);
  }
  return rows;
}

async function collectMetaInboxCandidates(page) {
  const rows = [];
  const seen = new Set();
  await page.goto('https://business.facebook.com/latest/inbox/all', { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => null);
  await page.waitForTimeout(5500);
  const readVisibleMessages = async (authorLabel, selectorName) => {
    const messages = await page.evaluate(() => {
      const blocked = new Set([
        'create messaging ad', 'automations', 'messaging insights', 'message settings',
        'priority', 'ad replies', 'follow up', 'assign this conversation', 'move to spam',
        'delete conversation', 'new message', 'all messages', 'primary', 'done', 'unread',
        'spam', 'search', 'settings', 'inbox', 'more items'
      ]);
      const nodes = [
        ...document.querySelectorAll('[role="main"] [role="article"]'),
        ...document.querySelectorAll('[role="main"] div[dir="auto"]'),
        ...document.querySelectorAll('[data-pagelet*="Inbox"] div[dir="auto"]'),
        ...document.querySelectorAll('[aria-label*="Conversation" i] div[dir="auto"]')
      ];
      const values = [];
      const seenText = new Set();
      for (const node of nodes) {
        const text = (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
        const lowered = text.toLowerCase();
        if (text.length < 3 || text.length > 1800 || blocked.has(lowered) || seenText.has(text)) continue;
        if (/^\d{1,2}:\d{2}\s*(am|pm)?$/i.test(text)) continue;
        if (!/[?.!,]/.test(text) && text.split(/\s+/).length <= 3) continue;
        seenText.add(text);
        values.push(text);
        if (values.length >= 50) break;
      }
      return values;
    }).catch(() => []);
    for (const text of messages) {
      const key = `${authorLabel}|${text}`;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push({ text, author: authorLabel, matchedSelector: selectorName });
      if (rows.length >= 60) return true;
    }
    return false;
  };
  await readVisibleMessages('Meta inbox', 'meta-visible-inbox');
  const threadSelectors = [
    '[role="main"] [role="row"]',
    '[role="main"] [role="listitem"]',
    '[data-pagelet*="Inbox"] [role="button"]',
    '[data-pagelet*="Inbox"] [role="link"]'
  ];
  let threads = page.locator(threadSelectors.join(', '));
  const count = Math.min(await threads.count().catch(() => 0), 10);
  for (let index = 0; index < count; index += 1) {
    threads = page.locator(threadSelectors.join(', '));
    const thread = threads.nth(index);
    const label = (await thread.innerText({ timeout: 1200 }).catch(() => '')).replace(/\s+/g, ' ').trim();
    await thread.click({ timeout: 4000 }).catch(() => null);
    await page.waitForTimeout(1600);
    if (await readVisibleMessages(label || 'Meta conversation', 'meta-conversation')) return rows;
  }
  return rows;
}

(async () => {
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0] || await browser.newContext();
  const results = [];
  for (const target of targets) {
    const page = await findPage(context, target);
    if (!page) {
      results.push({ platform: target.platform, skipped: true, reason: 'No logged-in comment tab', targetUrl: target.url });
      continue;
    }
    await page.bringToFront().catch(() => null);
    await page.waitForLoadState('domcontentloaded', { timeout: 15000 }).catch(() => null);
    await page.waitForTimeout(6500);
    for (let scroll = 0; scroll < 3; scroll += 1) {
      await page.mouse.wheel(0, 700).catch(() => null);
      await page.waitForTimeout(900);
    }
    const candidates = target.platform === 'x' && target.itemType === 'message'
      ? await collectXMessageCandidates(page)
      : target.platform === 'meta'
        ? await collectMetaInboxCandidates(page)
      : await collectGenericCandidates(page, target.selectors);
    results.push({ platform: target.platform, itemType: target.itemType, label: target.label, url: page.url(), targetUrl: target.url, candidates, gatheredAt: new Date().toISOString() });
  }
  fs.writeFileSync(outputPath, JSON.stringify({ gatheredAt: new Date().toISOString(), results }, null, 2), 'utf8');
  process.exit(0);
})().catch(error => {
  fs.writeFileSync(outputPath, JSON.stringify({ gatheredAt: new Date().toISOString(), error: error.message, stack: error.stack }, null, 2), 'utf8');
  process.exit(1);
});
