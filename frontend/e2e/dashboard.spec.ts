import { expect, test } from "@playwright/test";
import { signUpFresh, uploadAndWaitReady } from "./helpers";

test("ask, click citation highlights chunk, off-topic refuses", async ({ page }) => {
  await signUpFresh(page);
  await uploadAndWaitReady(page, "e2e/fixtures/handbook.md");
  await page.getByRole("tab", { name: "Dashboard" }).click();
  await page.getByLabel("Ask a question").fill("How long do refunds take?");
  await page.getByRole("button", { name: "Ask" }).click();
  await page.getByRole("button", { name: "Citation 1" }).click();
  const chunk = page.locator('[data-highlighted="true"]');
  await expect(chunk).toBeVisible();
  await expect(chunk).toContainText("14 days");
  await expect(chunk.getByRole("link", { name: "View in document" })).toHaveAttribute("href", /\/api\/documents\/.+\/file/);
  await page.getByLabel("Ask a question").fill("Who won the 1998 world cup?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByText("Not found in your documents")).toBeVisible();
});
