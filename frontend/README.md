# RAG Studio frontend

Next.js (App Router) + Tailwind. It proxies `/api/*` to the backend, so the backend must be running on `:8000`.

- `npm install`
- `npm run dev` starts the app on http://localhost:3000.
- `npx tsc --noEmit && npm run lint` type-checks and lints.
- `npx playwright test` runs the e2e tests. Playwright starts its own backend (fake LLM, hash embedder, throwaway DB under `backend/.e2e`) and the dev server, so nothing needs to be running first.
- First time only: `npx playwright install chromium`.
