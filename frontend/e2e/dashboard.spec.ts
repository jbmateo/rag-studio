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

test("ask 5xx without JSON shows friendly copy and Retry", async ({ page }) => {
  await signUpFresh(page);
  await page.route("**/api/ask", (r) => r.fulfill({ status: 500, body: "Internal Server Error" }));
  await page.getByLabel("Ask a question").fill("anything");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByText("The answer service is unavailable. Please try again.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("Sources panel shows load error with Retry", async ({ page }) => {
  await signUpFresh(page);
  await page.route("**/api/documents", (r) => r.fulfill({ status: 500, body: "boom" }));
  await page.reload();
  await expect(page.getByText("Couldn't load your documents.")).toBeVisible();
  await expect(page.getByText(/No ready documents/)).toHaveCount(0);
  await page.unroute("**/api/documents");
  await page.getByRole("region", { name: "Sources" }).getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText(/No ready documents/)).toBeVisible();
});
