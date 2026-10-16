import { expect, test, type Page } from "@playwright/test";
import { signUpFresh } from "./helpers";

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

// The backend allows 5 logins/min per IP, so the redirect cases stub the login call.
async function stubLogin(page: Page) {
  await page.route("**/api/auth/login", (r) =>
    r.fulfill({
      status: 200,
      headers: { "Set-Cookie": "session=stub; Path=/" },
      json: { id: "u1", email: "stub@x.io" },
    }));
  await page.route("**/api/auth/me", (r) => r.fulfill({ json: { id: "u1", email: "stub@x.io" } }));
  await page.route("**/api/documents", (r) => r.fulfill({ json: [] }));
}

async function loginWithNext(page: Page, next: string) {
  await stubLogin(page);
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email").fill("stub@x.io");
  await page.getByLabel("Password").fill("password1");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
  return new URL(page.url());
}

test("login ignores cross-origin next (backslash trick)", async ({ page }) => {
  const u = await loginWithNext(page, "/\\evil.example");
  expect(u.origin).toBe("http://localhost:3000");
  expect(u.pathname).toBe("/");
});

test("login honours a legitimate next with a query", async ({ page }) => {
  const u = await loginWithNext(page, "/?tab=documents");
  expect(u.origin + u.pathname + u.search).toBe("http://localhost:3000/?tab=documents");
});

test("login collapses leading slashes in next (/.//evil.example)", async ({ page }) => {
  const u = await loginWithNext(page, "/.//evil.example");
  expect(u.origin).toBe("http://localhost:3000");
  expect(u.pathname).toBe("/evil.example");
});

test("login falls back to / for a malformed next", async ({ page }) => {
  const u = await loginWithNext(page, "http://[");
  expect(u.origin).toBe("http://localhost:3000");
  expect(u.pathname).toBe("/");
  await expect(page.getByText("Something went wrong")).toHaveCount(0);
});
