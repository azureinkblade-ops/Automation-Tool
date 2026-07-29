const fs = require('fs');
const { chromium } = require('playwright');

const cdpUrl = "http://127.0.0.1:9222";
const outputPath = "C:\\Users\\David\\Documents\\Automation tool\\youtube-audience-fix-results.json";
const targets = [{"videoId": "KLcb2moSyZI", "title": "Heavenly Ascension System Chapter 7: Chapter 7: Trial of Spirit", "editUrl": "https://studio.youtube.com/video/KLcb2moSyZI/edit"}, {"videoId": "Qo0bFM6U9GA", "title": "Hundredfold Path Chapter 7: Chapter 7: The First Stirring of Technique", "editUrl": "https://studio.youtube.com/video/Qo0bFM6U9GA/edit"}, {"videoId": "aZUIDJDYCl8", "title": "Eternal Nexus Chapter 7: Chapter 7: The Emberfang Hunt", "editUrl": "https://studio.youtube.com/video/aZUIDJDYCl8/edit"}, {"videoId": "-swqQ6GZ15o", "title": "Eternal Nexus Chapter 6: Chapter 6: Into", "editUrl": "https://studio.youtube.com/video/-swqQ6GZ15o/edit"}, {"videoId": "OyCR_NqpVh4", "title": "Soul Forge Era Chapter 4: Chapter 4: The Forge's Lesson", "editUrl": "https://studio.youtube.com/video/OyCR_NqpVh4/edit"}, {"videoId": "PQIAXi5t20A", "title": "Heavenly Ascension System Chapter 5: Chapter 5: The Thing Beneath", "editUrl": "https://studio.youtube.com/video/PQIAXi5t20A/edit"}, {"videoId": "VCexnM6peds", "title": "Soul Forge Era Chapter 3: Chapter 3: Predator's Whisper", "editUrl": "https://studio.youtube.com/video/VCexnM6peds/edit"}, {"videoId": "s0OPriLwtX8", "title": "Eternal Nexus Chapter 5: Chapter 5: The Shadowforger's Path Expands", "editUrl": "https://studio.youtube.com/video/s0OPriLwtX8/edit"}, {"videoId": "pqdj3mugMNo", "title": "Hundredfold Path Chapter 5: Chapter 5: Embers of Rivalry", "editUrl": "https://studio.youtube.com/video/pqdj3mugMNo/edit"}, {"videoId": "L89VbNwmpNc", "title": "Heavenly Ascension System Chapter 4: Chapter 4: Echoes Beneath North Hollow", "editUrl": "https://studio.youtube.com/video/L89VbNwmpNc/edit"}, {"videoId": "VBV32jrf9tc", "title": "Hundredfold Path Chapter 4: Chapter 4: The First Breath", "editUrl": "https://studio.youtube.com/video/VBV32jrf9tc/edit"}, {"videoId": "84fav2LxoO0", "title": "Heavenly Ascension System Chapter 3: Chapter 3: The Weight Behind Smiles", "editUrl": "https://studio.youtube.com/video/84fav2LxoO0/edit"}, {"videoId": "RoCjPdO3IMA", "title": "Heavenly Ascension System Chapter 3: Chapter 3: The Weight Behind Smiles", "editUrl": "https://studio.youtube.com/video/RoCjPdO3IMA/edit"}, {"videoId": "PxcDroMxLW8", "title": "Hundredfold Path Chapter 3: Chapter 3: First Steps on", "editUrl": "https://studio.youtube.com/video/PxcDroMxLW8/edit"}, {"videoId": "dZHKOncXlJ8", "title": "Soul Forge Era Chapter 2: Chapter 2: The Price of Being Seen", "editUrl": "https://studio.youtube.com/video/dZHKOncXlJ8/edit"}, {"videoId": "VKuiRHVpjf0", "title": "Hundredfold Path Chapter 2: Chapter 2: The Jade Token", "editUrl": "https://studio.youtube.com/video/VKuiRHVpjf0/edit"}, {"videoId": "2Chxf7E6dIY", "title": "Heavenly Ascension System: Prologue", "editUrl": "https://studio.youtube.com/video/2Chxf7E6dIY/edit"}, {"videoId": "mp0Bumj4m3Q", "title": "Eternal Nexus Chapter 4: Chapter 4: Attention from", "editUrl": "https://studio.youtube.com/video/mp0Bumj4m3Q/edit"}, {"videoId": "TJ9oiJ-8N4w", "title": "Eternal Nexus Chapter 2: Chapter 2: First Hunt", "editUrl": "https://studio.youtube.com/video/TJ9oiJ-8N4w/edit"}, {"videoId": "pxo1QNUJV6k", "title": "Eternal Nexus Chapter 3: Chapter 3: Tempering", "editUrl": "https://studio.youtube.com/video/pxo1QNUJV6k/edit"}, {"videoId": "-iDB8DgowwQ", "title": "Eternal Nexus Chapter 1: Chapter 1: Patch 12.0", "editUrl": "https://studio.youtube.com/video/-iDB8DgowwQ/edit"}, {"videoId": "LMD0y7mlmA0", "title": "Eternal Nexus Chapter 3: Chapter 3: Tempering", "editUrl": "https://studio.youtube.com/video/LMD0y7mlmA0/edit"}, {"videoId": "lWskeVJ8yN4", "title": "Hundredfold Path Chapter 2: Chapter 2: The Jade Token", "editUrl": "https://studio.youtube.com/video/lWskeVJ8yN4/edit"}, {"videoId": "8potPvepJt8", "title": "Soul Forge Era Chapter 2: Chapter 2: The Price of Being Seen", "editUrl": "https://studio.youtube.com/video/8potPvepJt8/edit"}, {"videoId": "QAPmf9F0f9Q", "title": "Eternal Nexus Chapter 2: Chapter 2: First Hunt", "editUrl": "https://studio.youtube.com/video/QAPmf9F0f9Q/edit"}];

(async () => {
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0] || await browser.newContext();
  let page = context.pages().find((candidate) => {
    try { return new URL(candidate.url()).hostname === 'studio.youtube.com'; } catch (_) { return false; }
  });
  if (!page) page = await context.newPage();
  const results = [];
  for (const target of targets) {
    try {
      await page.goto(target.editUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
      const noKids = page.locator('[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]').first();
      await noKids.waitFor({ state: 'visible', timeout: 30000 });
      const before = await noKids.getAttribute('aria-checked');
      if (before !== 'true') {
        await noKids.scrollIntoViewIfNeeded();
        await noKids.click({ timeout: 5000 });
        await page.waitForFunction(() => document.querySelector('[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]')?.getAttribute('aria-checked') === 'true', null, { timeout: 10000 });
        const save = page.locator('#save button, button[aria-label="Save"]').first();
        await save.waitFor({ state: 'visible', timeout: 10000 });
        await page.waitForFunction(() => {
          const button = document.querySelector('#save');
          return button && !button.hasAttribute('disabled') && button.getAttribute('aria-disabled') !== 'true';
        }, null, { timeout: 10000 });
        const savedResponse = page.waitForResponse(
          (response) => response.url().includes('/youtubei/v1/video_manager/metadata_update') && response.request().method() === 'POST' && response.ok(),
          { timeout: 45000 }
        );
        await save.click({ timeout: 5000 });
        await savedResponse;
        await page.waitForFunction(() => document.querySelector('#save')?.getAttribute('aria-disabled') === 'true', null, { timeout: 30000 });
        await page.waitForTimeout(2500);
      }
      await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
      const verifyNoKids = page.locator('[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]').first();
      await verifyNoKids.waitFor({ state: 'visible', timeout: 30000 });
      const verified = await verifyNoKids.getAttribute('aria-checked') === 'true';
      results.push({ ...target, ok: verified, changed: before !== 'true', audience: verified ? 'not_made_for_kids' : 'unknown' });
    } catch (error) {
      results.push({ ...target, ok: false, changed: false, error: error.message });
    }
  }
  fs.writeFileSync(outputPath, JSON.stringify({ finishedAt: new Date().toISOString(), results }, null, 2), 'utf8');
  process.exit(0);
})().catch((error) => {
  fs.writeFileSync(outputPath, JSON.stringify({ finishedAt: new Date().toISOString(), error: error.message, stack: error.stack, results: [] }, null, 2), 'utf8');
  process.exit(1);
});
