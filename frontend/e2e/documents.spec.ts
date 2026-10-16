import { expect, test } from "@playwright/test";
import { signUpFresh } from "./helpers";

test("upload, see ready, import URL validation, delete", async ({ page }) => {
  await signUpFresh(page);
  await page.getByRole("tab", { name: "Documents" }).click();
  await expect(page).toHaveURL(/tab=documents/);
  await page.getByLabel("Upload files").setInputFiles("e2e/fixtures/handbook.md");
  const row = page.getByRole("row", { name: /handbook\.md/ });
  await expect(row.getByText(/Ready · \d+ chunks?/)).toBeVisible({ timeout: 15000 });
  await page.getByPlaceholder("https://…").fill("http://127.0.0.1/secret");
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("row", { name: /127\.0\.0\.1/ }).getByText("Failed")).toBeVisible({ timeout: 15000 });
  page.once("dialog", (d) => d.accept());
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(row).toHaveCount(0);
});
