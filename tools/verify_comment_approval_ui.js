const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on("console", message => {
    if (message.type() === "error" && !message.text().includes("Failed to load resource")) errors.push(message.text());
  });
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(process.env.AUTOMATION_TOOL_TEST_URL || "http://127.0.0.1:8876", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "Approval Inbox" }).click();
  await page.locator("#results .copy strong").filter({ hasText: "Approval Inbox" }).waitFor({ state: "visible" });
  await page.locator("#optionsPanel > summary").click();
  await page.locator("#optionSelect").selectOption("engagement");
  await page.getByRole("button", { name: "Gather Messages & Comments" }).waitFor({ state: "visible" });
  const outputDir = path.join(process.cwd(), "output", "playwright");
  fs.mkdirSync(outputDir, { recursive: true });
  const screenshot = path.join(outputDir, "approval-inbox.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  const approvalCards = await page.locator(".review-card").count();
  await page.locator("#optionSelect").selectOption("growth");
  await page.getByRole("button", { name: "Growth Opportunities" }).click();
  await page.locator("#results .copy strong").filter({ hasText: "Growth Opportunities" }).waitFor({ state: "visible" });
  const growthScreenshot = path.join(outputDir, "growth-opportunities.png");
  await page.screenshot({ path: growthScreenshot, fullPage: true });
  const result = {
    ok: errors.length === 0,
    errors,
    title: await page.title(),
    approvalCards,
    growthCards: await page.locator(".review-card").count(),
    screenshot,
    growthScreenshot,
  };
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
  if (!result.ok) process.exit(1);
})().catch(error => {
  console.error(error);
  process.exit(1);
});
