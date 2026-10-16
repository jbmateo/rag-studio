import { expect, test } from "@playwright/test";
import { signUpFresh, uploadAndWaitReady } from "./helpers";

// Regenerates the README screenshots: SCREENSHOTS=1 npx playwright test e2e/screenshots.spec.ts
test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to regenerate docs/screenshots");

for (const [name, size] of [["desktop", { width: 1280, height: 800 }], ["mobile", { width: 390, height: 844 }]] as const) {
  test(`dashboard screenshot (${name})`, async ({ page }) => {
    await page.setViewportSize(size);
    await signUpFresh(page);
    await uploadAndWaitReady(page, "e2e/fixtures/handbook.md");
    await page.getByRole("tab", { name: "Dashboard" }).click();
    await page.getByLabel("Ask a question").fill("How long do refunds take?");
    await page.getByRole("button", { name: "Ask" }).click();
    await page.getByRole("button", { name: "Citation 1" }).click();
    await expect(page.locator('[data-highlighted="true"]')).toBeVisible();
    await page.waitForTimeout(600);
    const noHScroll = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    expect(noHScroll).toBe(true);
    await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `../docs/screenshots/dashboard-${name}.png`, fullPage: name === "mobile" });
  });
}
