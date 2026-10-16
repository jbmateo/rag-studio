import { expect, test } from "@playwright/test";

test("signup, persists across reload, logout, bad login", async ({ page }) => {
  const email = `u${Date.now()}@x.io`;
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByRole("link", { name: "Create an account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password1");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByText(email)).toBeVisible();
  await page.reload();
  await expect(page.getByText(email)).toBeVisible();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("wrongpass1");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText("Invalid email or password")).toBeVisible();
});

test("helper signs up a fresh user and next redirect works", async ({ page }) => {
  await page.goto("/signup");
  await expect(page.getByRole("button", { name: "Sign up" })).toBeVisible();
  const { signUpFresh } = await import("./helpers");
  await page.context().clearCookies();
  const email = await signUpFresh(page);
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/?x=1");
  await expect(page).toHaveURL(/\/login\?next=/);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password1");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText(email)).toBeVisible();
});
