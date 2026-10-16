// Pre-compile dev routes so Next's first-compile full reload can't wipe a form mid-test.
export default async function globalSetup() {
  for (const path of ["/login", "/signup", "/"]) {
    await fetch(`http://localhost:3000${path}`, { redirect: "manual" });
  }
}
