const fs = require('fs');
const { chromium } = require('playwright');
const cdpUrl = "http://127.0.0.1:9222";
const jobId = "20260712-121009-HA-80";
const prompt = "Write the next chapter for the web novel Heavenly Ascension System.\n\nChapter number: 80\nChapter title: create a fitting chapter title unless the outline gives one\nTarget length: about 3000 words\n\nOutline:\nContinue naturally from the latest GitHub chapter. Resolve the immediate scene momentum, preserve character motivations, deepen the current arc, and end with a clear hook into the next chapter.\n\nContinuity and style notes:\nNovel: Heavenly Ascension System\n\nLatest chapter in GitHub Docs: 79\n\nLast chapter summary: And all of them wore Li Yun's face. The dead rose across the mortal world. Some sat upright in beds. Some pushed themselves from blood-dark streets.\n\nTone/style notes: Preserve the established prose style, pacing, POV discipline, character motivations, and current arc momentum.\n\nNext chapter setup: \"It created it to erase the only person who remembered what it was called. \"\n\nRecent chapter check 79: Chapter 79: What the Dead Called Him\nChapter 79: What the Dead Called Him And all of them wore Li Yun's face. The dead rose across the mortal world. Some sat upright in beds. Some pushed themselves from blood-dark streets. Some opened their eyes beneath collapsed formation halls, hidden market stalls, sect courtyards, hospital lights, and mountain snow. Their wounds remained. Their bodies remained dead. Only their faces changed. Li Yun saw himself everywhere. Older. Younger. Male. Female. Human. Spirit. His abandoned features stretched across every shape the trial had killed. The same dark hair. The same eyes. The same mouth. Thousands of stolen versions of him looked toward the living. Then they spoke. \"You did this.\" The accu\n\nRequirements:\n- Preserve continuity and character motivations from the notes.\n- Write polished prose, not an outline.\n- Include one clear chapter title at the top.\n- End with forward momentum into the next chapter.\n- Do not include marketing copy, author notes, explanations, analysis, markdown tables, or code blocks.\n- Use normal paragraph spacing.\n- Use hyphens instead of em dashes.\n\nReturn only:\nTitle line\nChapter prose\n";
const targetWords = 3000;
const outputPath = "C:\\Users\\David\\Documents\\Automation tool\\chatgpt-chapter-result.json";

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
  throw new Error('ChatGPT did not finish the chapter before the 12-minute timeout. The conversation remains open for review.');
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
  let chapterText = await waitForCompletedResponse(page, baseline);
  let words = chapterText.split(/\s+/).filter(Boolean).length;
  for (let continuation = 0; words < Math.floor(targetWords * 0.9) && continuation < 2; continuation++) {
    const messages = await assistantMessages(page);
    const nextBaseline = await messages.count();
    await submitPrompt(page, `Continue the same chapter from the exact stopping point. Add enough polished prose to reach at least ${targetWords} total words. Do not repeat the title or earlier text. Return only the remaining chapter prose.`);
    const addition = await waitForCompletedResponse(page, nextBaseline);
    chapterText = `${chapterText}\n\n${addition}`.trim();
    words = chapterText.split(/\s+/).filter(Boolean).length;
  }
  fs.writeFileSync(outputPath, JSON.stringify({
    ok: true, jobId, chapterText, wordCount: words, sourceUrl: page.url(), completedAt: new Date().toISOString(), submitted: false
  }, null, 2), 'utf8');
  process.exit(0);
})().catch(error => {
  fs.writeFileSync(outputPath, JSON.stringify({ ok: false, jobId, error: error.message, stack: error.stack, completedAt: new Date().toISOString() }, null, 2), 'utf8');
  process.exit(1);
});
