const fs = require('fs');
const { chromium } = require('playwright');
const cdpUrl = "http://127.0.0.1:9222";
const jobId = "20260718-110856-HA-story-hook";
const prompt = "Create an original standalone YouTube story script for Azure Inkblade.\n\nPurpose:\n- Make a full YouTube video that feels like a high-retention Reddit-style fantasy/progression story.\n- Do not use, quote, summarize, or imitate any real Reddit post.\n- Do not mention Reddit in the final script unless it is part of an AITA-style title.\n- The story must be original fiction and can act as an entry funnel into Heavenly Ascension System.\n- Focus on a title/hook that maximizes curiosity, clicks, retention, and reader conversion.\n\nNovel universe: Heavenly Ascension System\nCurrent arc/context: use the series premise and genre flavor\nContinuity signal: The first morning without heaven had begun, and already someone was trying to build it again.\nAngle: hidden power\nSuggested title pattern: hidden power\nTarget length: 2600 words.\n\nRules:\n- No em dash characters.\n- Keep the prose punchy, clear, and emotionally direct.\n- Start with a strong first-person or close-third hook in the first sentence.\n- Structure it like a complete mini story with escalation, betrayal/conflict, reversal, and payoff.\n- Make the situation emotionally obvious within the first 20 seconds.\n- Include one comment-worthy moral question or decision point inside the story.\n- Dark, horror, dread, and unsettling supernatural stakes are allowed when the archetype calls for it, but avoid explicit gore, sexual violence, real-world hate, or shock content that could hurt monetization.\n- Avoid direct Patreon selling inside the story body.\n- End with a short call to action that points viewers to the related Azure Inkblade novel on Royal Road and YouTube.\n- Return only valid JSON with these exact keys:\n  \"title\": clickable YouTube title under 90 characters,\n  \"story\": full narration script,\n  \"description\": short YouTube description with Royal Road, Patreon, YouTube, TikTok, Instagram, and X links,\n  \"tags\": array of 8 to 15 search tags,\n  \"relatedNovel\": \"HA\",\n  \"hookAngle\": \"hidden power\"";
const targetWords = 2600;
const outputPath = "C:\\Users\\David\\Documents\\Automation tool\\story-hook-chatgpt-result.json";

async function findEditor(page) {
  const candidates = [
    page.locator('#prompt-textarea').first(),
    page.locator('[contenteditable="true"][data-lexical-editor="true"]').first(),
    page.locator('textarea[placeholder*="Message" i]').first(),
    page.locator('textarea').first(),
  ];
  for (const candidate of candidates) {
    if (await candidate.count() && await candidate.isVisible().catch(() => false)) return candidate;
  }
  return null;
}

async function submitPrompt(page, text) {
  const editor = await findEditor(page);
  if (!editor) throw new Error('ChatGPT prompt box was not found. Open chatgpt.com, sign in, and retry.');
  await editor.click();
  await page.keyboard.press('Control+A');
  await page.keyboard.insertText(text);
  const send = page.locator('button[data-testid="send-button"], button[aria-label*="Send" i]').last();
  if (await send.count() && await send.isEnabled().catch(() => false)) await send.click();
  else await page.keyboard.press('Enter');
}

async function assistantMessages(page) {
  const primary = page.locator('[data-message-author-role="assistant"]');
  if (await primary.count()) return primary;
  return page.locator('article[data-testid^="conversation-turn"]');
}

async function waitForCompletedResponse(page, baseline) {
  await page.waitForFunction(
    (start) => document.querySelectorAll('[data-message-author-role="assistant"]').length > start,
    baseline,
    { timeout: 240000 }
  ).catch(() => null);
  let stableText = '';
  let stablePasses = 0;
  const deadline = Date.now() + 720000;
  while (Date.now() < deadline) {
    const messages = await assistantMessages(page);
    const count = await messages.count();
    const parts = [];
    for (let index = baseline; index < count; index++) {
      const value = (await messages.nth(index).innerText().catch(() => '')).trim();
      if (value) parts.push(value);
    }
    const text = parts.join('\n\n').trim();
    const stopVisible = await page.locator('button[data-testid="stop-button"], button[aria-label*="Stop" i]').first().isVisible().catch(() => false);
    if (text.length > 300 && text === stableText && !stopVisible) stablePasses += 1;
    else stablePasses = 0;
    stableText = text;
    if (stablePasses >= 3) return stableText;
    await page.waitForTimeout(2000);
  }
  throw new Error('ChatGPT did not finish the story hook before the 12-minute timeout. The conversation remains open for review.');
}

(async () => {
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0] || await browser.newContext();
  let page = context.pages().find(candidate => {
    try { return ['chatgpt.com', 'chat.openai.com'].includes(new URL(candidate.url()).hostname.replace(/^www\./, '')); }
    catch (_) { return false; }
  });
  if (!page) {
    page = await context.newPage();
    await page.goto('https://chatgpt.com/', { waitUntil: 'domcontentloaded', timeout: 45000 });
  }
  await page.bringToFront();
  await page.waitForLoadState('domcontentloaded', { timeout: 30000 }).catch(() => null);
  await page.waitForTimeout(1500);
  const before = await assistantMessages(page);
  const baseline = await before.count();
  await submitPrompt(page, prompt);
  const storyText = await waitForCompletedResponse(page, baseline);
  fs.writeFileSync(outputPath, JSON.stringify({
    ok: true, jobId, storyText, wordCount: storyText.split(/\s+/).filter(Boolean).length, sourceUrl: page.url(), completedAt: new Date().toISOString()
  }, null, 2), 'utf8');
  process.exit(0);
})().catch(error => {
  fs.writeFileSync(outputPath, JSON.stringify({ ok: false, jobId, error: error.message, stack: error.stack, completedAt: new Date().toISOString() }, null, 2), 'utf8');
  process.exit(1);
});
