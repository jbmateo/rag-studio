import { NextResponse, type NextRequest } from "next/server";

// Only checks that the session cookie exists. Real validity is enforced by the API (401),
// which api() turns into a redirect to /login.
export function middleware(req: NextRequest) {
  if (req.cookies.has("session")) return NextResponse.next();
  const url = req.nextUrl.clone();
  const next = req.nextUrl.pathname + req.nextUrl.search;
  url.pathname = "/login";
  url.search = "";
  url.searchParams.set("next", next);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!login|signup|api/|_next/|favicon\\.ico).*)"],
};
