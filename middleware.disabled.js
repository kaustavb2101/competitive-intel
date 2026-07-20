// Access protection for the AutoX / เงินไชโย credit-intelligence platform (sensitive branch-level PD).
//
// Vercel Edge Middleware — runs before every request and requires HTTP Basic Auth when a password is
// configured. Share the site with colleagues by giving them the password (no Vercel account needed).
//
// ACTIVATION (one step, owner):
//   Vercel → project `competitive-intel` → Settings → Environment Variables →
//   add  SITE_PASSWORD = <your chosen password>  (Production; add Preview too if you want it gated),
//   then redeploy (or just push any commit). The browser will prompt for a password (any username).
//
// SAFE BY DESIGN: if SITE_PASSWORD is unset/empty the middleware is a no-op (site stays public) — so
// deploying this can NEVER lock anyone out; protection turns on ONLY once you set the password. Any
// unexpected error also fails OPEN so the site never breaks.
//
// To turn protection OFF again: delete the SITE_PASSWORD env var and redeploy.

export const config = {
  // Protect everything. (Static assets, data JSON, and every route all require the password once set.)
  matcher: '/:path*',
};

export default function middleware(request) {
  try {
    const pass = (process.env.SITE_PASSWORD || '').trim();
    if (!pass) return; // no password configured -> public (no lockout, no breakage)

    const auth = request.headers.get('authorization') || '';
    const m = auth.match(/^Basic\s+(.+)$/i);
    if (m) {
      let decoded = '';
      try { decoded = atob(m[1]); } catch (e) { decoded = ''; }
      const i = decoded.indexOf(':');
      const supplied = i >= 0 ? decoded.slice(i + 1) : decoded; // accept any username; check password
      if (supplied === pass) return; // authorized
    }

    return new Response('Restricted - AutoX Credit Intelligence. A password is required.', {
      status: 401,
      headers: {
        // NOTE: HTTP header values must be ASCII (ISO-8859-1). A non-ASCII char here (e.g. an em-dash)
        // makes the edge silently DROP this header, so the browser never shows its native login prompt
        // and the user is stuck on the 401 body with no way in. Keep the realm strictly ASCII.
        'WWW-Authenticate': 'Basic realm="AutoX Credit Intelligence", charset="UTF-8"',
        'Cache-Control': 'no-store',
      },
    });
  } catch (e) {
    return; // fail OPEN on any unexpected error — never break the live site
  }
}
