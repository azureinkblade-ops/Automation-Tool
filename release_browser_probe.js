const fs = require('fs');
const { chromium } = require('playwright');

const cdpUrl = process.env.CHROME_DEBUG_URL || 'http://127.0.0.1:9222';
const output = process.argv[2] || 'release-browser-probe.json';
const openTierPicker = process.argv.includes('--open-tiers');
const openTierMenu = process.argv.includes('--open-tier-menu');
const selectInnerOnly = process.argv.includes('--select-inner-only');
const targetUrlArg = process.argv.find(value => value.startsWith('--url='));
const targetUrl = targetUrlArg ? targetUrlArg.slice('--url='.length) : '';

(async () => {
  const browser = await chromium.connectOverCDP(cdpUrl);
  const contexts = browser.contexts();
  if (targetUrl) {
    const context = contexts[0] || await browser.newContext();
    const page = await context.newPage();
    await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(3000);
  }
  const pages = contexts.flatMap(context => context.pages());
  const results = [];
  for (const page of pages) {
    const url = page.url();
    if (!/patreon\.com|royalroad\.com/i.test(url)) continue;
    if (openTierPicker && /patreon\.com/i.test(url)) {
      const tierToggle = page.locator('input[type="checkbox"][aria-label="Toggle tier selection"]:visible').first();
      if (await tierToggle.count().catch(() => 0)) {
        await tierToggle.check({ force: true }).catch(() => null);
        await page.waitForTimeout(700);
      }
      if (openTierMenu) {
        const selectTiers = page.getByRole('button', { name: 'Select tiers' }).first();
        if (await selectTiers.count().catch(() => 0)) {
          if ((await selectTiers.getAttribute('aria-expanded')) !== 'true') {
            await selectTiers.click({ force: true }).catch(() => null);
            await page.waitForTimeout(700);
          }
        }
      }
      if (selectInnerOnly) {
        for (const [tier, wanted] of [['Path Initiate', false], ['Inner Disciple', true]]) {
          const tierItem = page.getByRole('menuitemcheckbox').filter({ hasText: tier }).first();
          if (await tierItem.count().catch(() => 0)) {
            const checked = (await tierItem.getAttribute('aria-checked')) === 'true';
            if (checked !== wanted) await tierItem.click({ force: true });
            await page.waitForTimeout(350);
          }
        }
        await page.keyboard.press('Escape').catch(() => null);
        await page.waitForTimeout(500);
      }
    }
    const controls = await page.locator('button:visible, [role="button"]:visible, input[type="submit"]:visible').evaluateAll(elements =>
      elements.slice(0, 80).map(element => ({
        tag: element.tagName.toLowerCase(),
        text: String(element.innerText || element.value || element.getAttribute('aria-label') || '').trim().slice(0, 160),
        type: element.getAttribute('type') || '',
        testId: element.getAttribute('data-testid') || '',
        ariaLabel: element.getAttribute('aria-label') || '',
        ariaPressed: element.getAttribute('aria-pressed') || '',
        ariaSelected: element.getAttribute('aria-selected') || '',
        dataState: element.getAttribute('data-state') || '',
        className: String(element.className || '').slice(0, 240),
        html: String(element.outerHTML || '').slice(0, 900),
        disabled: Boolean(element.disabled || element.getAttribute('aria-disabled') === 'true'),
      }))
    );
    const diagnostics = await page.locator('input:visible, textarea:visible, [role="alert"]:visible, [aria-invalid="true"]:visible').evaluateAll(elements =>
      elements.slice(0, 80).map(element => ({
        tag: element.tagName.toLowerCase(),
        type: element.getAttribute('type') || '',
        name: element.getAttribute('name') || '',
        placeholder: element.getAttribute('placeholder') || '',
        value: String(element.value || '').slice(0, 160),
        text: String(element.innerText || element.textContent || '').trim().slice(0, 240),
        ariaInvalid: element.getAttribute('aria-invalid') || '',
      }))
    );
    const editors = await page.locator('[contenteditable="true"]:visible').evaluateAll(elements =>
      elements.slice(0, 20).map(element => ({
        role: element.getAttribute('role') || '',
        ariaLabel: element.getAttribute('aria-label') || '',
        textLength: String(element.innerText || element.textContent || '').trim().length,
        textStart: String(element.innerText || element.textContent || '').trim().slice(0, 160),
      }))
    );
    const iframes = await page.locator('iframe').evaluateAll(elements =>
      elements.slice(0, 20).map(element => ({
        id: element.id || '',
        name: element.getAttribute('name') || '',
        title: element.getAttribute('title') || '',
        className: String(element.className || '').slice(0, 200),
      }))
    );
    const forms = await page.locator('form').evaluateAll(elements =>
      elements.slice(0, 12).map(element => ({
        id: element.id || '',
        action: element.getAttribute('action') || '',
        method: element.getAttribute('method') || '',
        controls: [...element.querySelectorAll('input, textarea, button, select')].slice(0, 80).map(control => ({
          tag: control.tagName.toLowerCase(),
          type: control.getAttribute('type') || '',
          name: control.getAttribute('name') || '',
          id: control.id || '',
          value: String(control.value || '').slice(0, 200),
          text: String(control.innerText || '').trim().slice(0, 120),
        })),
      }))
    );
    const selections = await page.locator('input[type="radio"]:visible, input[type="checkbox"]:visible').evaluateAll(elements =>
      elements.map(element => ({
        type: element.type,
        value: element.value,
        checked: Boolean(element.checked),
        ariaLabel: element.getAttribute('aria-label') || '',
        parentText: String(element.parentElement?.parentElement?.innerText || element.parentElement?.innerText || '').trim().slice(0, 300),
        ancestors: Array.from((function* () {
          let current = element;
          for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) yield current;
        })()).map((ancestor, depth) => ({
          depth,
          tag: ancestor.tagName.toLowerCase(),
          role: ancestor.getAttribute('role') || '',
          ariaLabel: ancestor.getAttribute('aria-label') || '',
          testId: ancestor.getAttribute('data-testid') || '',
          text: String(ancestor.innerText || '').trim().slice(0, 500),
        })),
      }))
    );
    const bodyText = String(await page.locator('body').innerText().catch(() => '')).slice(0, 30000);
    const links = await page.locator('a').evaluateAll(elements =>
      elements.slice(0, 500).map(element => ({
        text: String(element.innerText || element.textContent || '').trim().slice(0, 300),
        href: element.href || element.getAttribute('href') || '',
        ariaLabel: element.getAttribute('aria-label') || '',
      }))
    );
    const tableRows = await page.locator('table tr').evaluateAll(rows =>
      rows.slice(0, 500).map(row => ({
        text: String(row.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 1000),
        links: Array.from(row.querySelectorAll('a')).map(link => ({
          text: String(link.innerText || link.textContent || '').trim().slice(0, 200),
          href: link.href || link.getAttribute('href') || '',
        })),
        buttons: Array.from(row.querySelectorAll('button, input[type="submit"]')).map(button => ({
          text: String(button.innerText || button.value || '').trim().slice(0, 200),
          name: button.getAttribute('name') || '',
          value: button.getAttribute('value') || '',
        })),
      }))
    );
    results.push({ url, title: await page.title(), controls, diagnostics, editors, iframes, forms, selections, bodyText, links, tableRows });
  }
  fs.writeFileSync(output, JSON.stringify({ capturedAt: new Date().toISOString(), results }, null, 2), 'utf8');
  process.exit(0);
})().catch(error => {
  fs.writeFileSync(output, JSON.stringify({ capturedAt: new Date().toISOString(), error: error.message }, null, 2), 'utf8');
  process.exit(1);
});
