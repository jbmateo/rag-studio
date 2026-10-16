import { expect, type Page } from "@playwright/test";

/** Signs up a unique user via the UI and waits until the header shows their email. */
export async function signUpFresh(page: Page): Promise<string> {
  const email = `u${Date.now()}${Math.floor(Math.random() * 1e6)}@x.io`;
  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password1");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByText(email)).toBeVisible();
  return email;
}

/** Opens the Documents tab, uploads a file and waits until it is Ready. */
export async function uploadAndWaitReady(page: Page, path: string): Promise<void> {
  await page.getByRole("tab", { name: "Documents" }).click();
  await page.getByLabel("Upload files").setInputFiles(path);
  await expect(page.getByText(/Ready · \d+ chunks?/)).toBeVisible({ timeout: 15000 });
}
