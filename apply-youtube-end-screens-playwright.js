const fs = require('fs');
const { chromium } = require('playwright');

const cdpUrl = "http://127.0.0.1:9222";
const outputPath = "C:\\Users\\David\\Documents\\Automation tool\\youtube-end-screen-results.json";
const targets = [{"videoId": "vIyzIoMxJzk", "title": "Hundredfold Path Chapter 21: Chapter 21: Blood on", "editUrl": "https://studio.youtube.com/video/vIyzIoMxJzk/edit", "novel": "Hundredfold Path", "chapter": 21, "elements": [{"type": "subscribe", "label": "Subscribe to Azure Inkblade"}, {"type": "best_for_viewer", "label": "Best video for this viewer"}, {"type": "playlist", "label": "Hundredfold Path playlist"}, {"type": "video", "label": "Hundredfold Path Chapter 22"}], "targetVideo": {"type": "video", "label": "Hundredfold Path Chapter 22"}}, {"videoId": "60QGQFZNwZY", "title": "Soul Forge Era Chapter 21: Chapter 21: Paper Teeth", "editUrl": "https://studio.youtube.com/video/60QGQFZNwZY/edit", "novel": "Soul Forge Era", "chapter": 21, "elements": [{"type": "subscribe", "label": "Subscribe to Azure Inkblade"}, {"type": "best_for_viewer", "label": "Best video for this viewer"}, {"type": "playlist", "label": "Soul Forge Era playlist"}, {"type": "video", "label": "Soul Forge Era Chapter 22"}], "targetVideo": {"type": "video", "label": "Soul Forge Era Chapter 22"}}, {"videoId": "X2QYV0gX--Q", "title": "Heavenly Ascension System Chapter 21: Chapter 21: River of Shadows", "editUrl": "https://studio.youtube.com/video/X2QYV0gX--Q/edit", "novel": "Heavenly Ascension System", "chapter": 21, "elements": [{"type": "subscribe", "label": "Subscribe to Azure Inkblade"}, {"type": "best_for_viewer", "label": "Best video for this viewer"}, {"type": "playlist", "label": "Heavenly Ascension System playlist"}, {"type": "video", "label": "Heavenly Ascension System Chapter 22"}], "targetVideo": {"type": "video", "label": "Heavenly Ascension System Chapter 22"}}, {"videoId": "1h4JSTCvJvw", "title": "Eternal Nexus Chapter 21: Chapter 21: The Hunt Resumes", "editUrl": "https://studio.youtube.com/video/1h4JSTCvJvw/edit", "novel": "Eternal Nexus", "chapter": 21, "elements": [{"type": "subscribe", "label": "Subscribe to Azure Inkblade"}, {"type": "best_for_viewer", "label": "Best video for this viewer"}, {"type": "playlist", "label": "Eternal Nexus playlist"}, {"type": "video", "label": "Eternal Nexus Chapter 22"}], "targetVideo": {"type": "video", "label": "Eternal Nexus Chapter 22"}}, {"videoId": "XB7mGMgiDN4", "title": "Hundredfold Path Chapter 19: Chapter 19: The Hidden Scroll", "editUrl": "https://studio.youtube.com/video/XB7mGMgiDN4/edit", "novel": "Hundredfold Path", "chapter": 19, "elements": [{"type": "subscribe", "label": "Subscribe to Azure Inkblade"}, {"type": "best_for_viewer", "label": "Best video for this viewer"}, {"type": "playlist", "label": "Hundredfold Path playlist"}, {"type": "video", "label": "Hundredfold Path Chapter 20: Chapter 20: The Weight of Breath", "targetVideoId": "Xv4hWs8JHqg", "targetTitle": "Hundredfold Path Chapter 20: Chapter 20: The Weight of Breath", "targetWatchUrl": "https://www.youtube.com/watch?v=Xv4hWs8JHqg"}], "targetVideo": {"type": "video", "label": "Hundredfold Path Chapter 20: Chapter 20: The Weight of Breath", "targetVideoId": "Xv4hWs8JHqg", "targetTitle": "Hundredfold Path Chapter 20: Chapter 20: The Weight of Breath", "targetWatchUrl": "https://www.youtube.com/watch?v=Xv4hWs8JHqg"}}];
const screenshotDir = "C:\\Users\\David\\Documents\\Automation tool\\youtube-end-screen-debug";
fs.mkdirSync(screenshotDir, { recursive: true });

async function clickFirst(page, labels, timeout = 3500) {
  for (const label of labels) {
    for (const role of ['button', 'tab', 'link', 'menuitem']) {
      const byRole = page.getByRole(role, { name: label }).first();
      if (await byRole.count().catch(() => 0)) {
        try {
          await byRole.click({ timeout });
          return `${role}:${label}`;
        } catch (_) {}
      }
    }
    const byText = page.getByText(label, { exact: false }).first();
    if (await byText.count().catch(() => 0)) {
      try {
        await byText.click({ timeout });
        return `text:${label}`;
      } catch (_) {}
    }
  }
  return '';
}

async function clickVisibleSelector(page, selectors, timeout = 3500) {
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    if (!(await locator.count().catch(() => 0))) continue;
    try {
      await locator.scrollIntoViewIfNeeded().catch(() => null);
      await locator.click({ timeout });
      return selector;
    } catch (_) {}
  }
  return '';
}

async function clickTextDom(page, needles) {
  return await page.evaluate((rawNeedles) => {
    const wanted = rawNeedles.map((value) => String(value || '').toLowerCase()).filter(Boolean);
    const visible = (el) => {
      const box = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      return box.width > 0 && box.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    };
    const nodes = Array.from(document.querySelectorAll('ytcp-button, ytcp-icon-button, tp-yt-paper-item, yt-formatted-string, button, a, div, span'));
    for (const node of nodes) {
      if (!visible(node)) continue;
      const text = String(node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
      if (!text || !wanted.some((needle) => text.includes(needle))) continue;
      const clickable = node.closest('button, a, ytcp-button, ytcp-icon-button, tp-yt-paper-item') || node;
      clickable.click();
      return text.slice(0, 120);
    }
    return '';
  }, needles).catch(() => '');
}

async function pageTextSample(page) {
  return await page.evaluate(() => String(document.body?.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 1800)).catch(() => '');
}

async function debugCapture(page, row, label) {
  const safeId = String(row.videoId || 'unknown').replace(/[^A-Za-z0-9_-]/g, '_');
  const path = `${screenshotDir}/${safeId}-${label}.png`;
  await page.screenshot({ path, fullPage: true }).catch(() => null);
  row.debugScreenshot = path;
  row.pageText = await pageTextSample(page);
  row.currentUrl = page.url();
}

async function chooseSpecificEndScreenVideo(page, target) {
  const targetVideo = target.targetVideo || {};
  const targetId = String(targetVideo.targetVideoId || '');
  const targetTitle = String(targetVideo.targetTitle || targetVideo.label || '');
  if (!targetId && !targetTitle) return 'no specific target video';
  const addVideo = await clickFirst(page, ['Add Video', 'Video'], 5000)
    || await clickTextDom(page, ['add video', 'video']);
  if (!addVideo) return 'add video control not found';
  await page.waitForTimeout(1500);
  const chooseSpecific = await clickFirst(page, ['Choose specific video', 'Specific video', 'Choose video'], 5000)
    || await clickTextDom(page, ['choose specific video', 'specific video', 'choose video']);
  await page.waitForTimeout(1500);
  const search = page.locator('input[placeholder*="Search" i], input[aria-label*="Search" i], ytcp-search-box input, input[type="text"]').first();
  if (await search.count().catch(() => 0)) {
    await search.click({ timeout: 3000 }).catch(() => null);
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A').catch(() => null);
    await page.keyboard.press('Backspace').catch(() => null);
    await page.keyboard.insertText(targetId || targetTitle);
    await page.waitForTimeout(2500);
  }
  const selected = await clickVisibleSelector(page, [
    `a[href*="${targetId}"]`,
    `ytcp-video-list-cell-video-renderer:has-text("${targetTitle.replace(/"/g, '\"')}")`,
    `ytcp-video-row:has-text("${targetTitle.replace(/"/g, '\"')}")`,
    `tp-yt-paper-item:has-text("${targetTitle.replace(/"/g, '\"')}")`
  ], 5000) || await clickTextDom(page, [targetTitle, targetId]);
  if (!selected) return `specific target not found: ${targetTitle || targetId}`;
  await page.waitForTimeout(1000);
  const apply = await clickFirst(page, ['Apply', 'Save', 'Done'], 5000)
    || await clickTextDom(page, ['apply', 'save', 'done']);
  await page.waitForTimeout(1500);
  return `selected specific video ${targetId || targetTitle} via ${selected}${apply ? '; applied' : ''}${chooseSpecific ? '; specific mode' : ''}`;
}

async function saveIfPossible(page) {
  const save = page.locator('#save button, button[aria-label="Save"], ytcp-button:has-text("Save")').first();
  if (!(await save.count().catch(() => 0))) return false;
  try {
    await save.scrollIntoViewIfNeeded().catch(() => null);
    const disabled = await save.getAttribute('disabled').catch(() => null);
    const ariaDisabled = await save.getAttribute('aria-disabled').catch(() => null);
    if (disabled !== null || ariaDisabled === 'true') return false;
    const response = page.waitForResponse(
      (res) => res.request().method() === 'POST' && /youtubei\/v1\//.test(res.url()) && res.ok(),
      { timeout: 45000 }
    ).catch(() => null);
    await save.click({ timeout: 5000 });
    await response;
    await page.waitForTimeout(2500);
    return true;
  } catch (_) {
    return false;
  }
}

(async () => {
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0] || await browser.newContext();
  const results = [];
  for (const target of targets) {
    const page = await context.newPage();
    const row = { ...target, ok: false, steps: [], saved: false, needsManualReview: true };
    try {
      await page.goto(target.editUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.bringToFront().catch(() => null);
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => null);
      await page.waitForTimeout(2500);
      row.steps.push('opened_edit_page');

      const editorUrl = `https://studio.youtube.com/video/${target.videoId}/editor`;
      await page.goto(editorUrl, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => null);
      await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => null);
      await page.waitForTimeout(4500);
      row.steps.push('opened_editor_url');

      const editorClick = await clickFirst(page, [/^Editor$/i, 'Editor', 'Video editor'], 4000)
        || await clickTextDom(page, ['editor', 'video editor']);
      if (editorClick) {
        row.steps.push(`opened_editor:${editorClick}`);
        await page.waitForTimeout(4500);
      }

      const endScreenClick = await clickFirst(page, [/End screen/i, 'End screen', 'Add an end screen', 'Add end screen'], 5000)
        || await clickVisibleSelector(page, [
          'ytcp-ve-expansion-panel:has-text("End screen")',
          'ytcp-button:has-text("End screen")',
          'button:has-text("End screen")',
          '[aria-label*="End screen" i]',
          '[test-id*="end" i]',
          '[id*="end" i]'
        ], 5000)
        || await clickTextDom(page, ['end screen', 'add an end screen']);
      if (endScreenClick) {
        row.steps.push(`opened_end_screen:${endScreenClick}`);
        await page.waitForTimeout(3500);
      } else {
        await debugCapture(page, row, 'no-end-screen-control');
        throw new Error('Could not find the YouTube Studio End screen control.');
      }

      const specificVideoResult = await chooseSpecificEndScreenVideo(page, target);
      row.steps.push(`specific_video:${specificVideoResult}`);
      const specificVideoSelected = specificVideoResult.startsWith('selected specific video');

      const importClick = specificVideoSelected ? '' : await clickFirst(page, ['Import from video', 'Import from latest video', 'Use template', 'Apply template', 'Import'], 5000)
        || await clickTextDom(page, ['import from video', 'import from latest video', 'use template', 'apply template', 'import']);
      if (importClick) {
        row.steps.push(`attempted_template:${importClick}`);
        await page.waitForTimeout(3000);
        const dialogChoice = await clickVisibleSelector(page, [
          'ytcp-video-list-cell-video-renderer:visible',
          'tp-yt-paper-dialog ytcp-entity-card:visible',
          'tp-yt-paper-dialog ytcp-video-row:visible'
        ], 4000);
        if (dialogChoice) {
          row.steps.push(`selected_template_source:${dialogChoice}`);
          await page.waitForTimeout(1200);
        }
        const applyTemplate = await clickFirst(page, ['Import', 'Apply', 'Done', 'Save'], 5000)
          || await clickTextDom(page, ['import', 'apply', 'done']);
        if (applyTemplate) {
          row.steps.push(`applied_template:${applyTemplate}`);
          await page.waitForTimeout(2500);
        }
      }

      for (const label of ['Subscribe', 'Best for viewer', 'Video', 'Playlist', 'Most recent upload']) {
        if (specificVideoSelected && label === 'Video') continue;
        const clicked = await clickFirst(page, [`Add ${label}`, label], 2500);
        if (clicked) {
          row.steps.push(`attempted_element:${label}`);
          await page.waitForTimeout(1200);
        }
      }

      row.saved = await saveIfPossible(page);
      row.ok = row.saved || row.steps.some((step) => step.startsWith('opened_end_screen'));
      row.needsManualReview = !row.saved;
      if (!row.saved) {
        await debugCapture(page, row, 'not-saved');
        row.note = 'YouTube Studio opened the end-screen workflow, but the app could not verify a saved end-screen. Review this video manually.';
      }
    } catch (error) {
      row.error = error.message;
      await debugCapture(page, row, 'error').catch(() => null);
    } finally {
      if (row.saved || row.error) {
        await page.close().catch(() => null);
      } else {
        row.steps.push('left_open_for_manual_review');
      }
    }
    results.push(row);
    fs.writeFileSync(outputPath, JSON.stringify({ updatedAt: new Date().toISOString(), results }, null, 2), 'utf8');
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
  fs.writeFileSync(outputPath, JSON.stringify({ finishedAt: new Date().toISOString(), results }, null, 2), 'utf8');
  process.exit(0);
})().catch((error) => {
  fs.writeFileSync(outputPath, JSON.stringify({ finishedAt: new Date().toISOString(), error: error.message, stack: error.stack, results: [] }, null, 2), 'utf8');
  process.exit(1);
});
