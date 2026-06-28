# AutoX / เงินไชโย — Credit Intelligence

Branch-intelligence platform over all 2,015 AutoX branches + Rayong deep-dives.
Static site (deploys to Vercel) backed by a Python data pipeline.

**Start here:** open `CLAUDE.md` (full project context — Claude Code reads it automatically),
then `docs/PROGRESS_LOG.md` (what's done) and `docs/NEXT_STEPS.md` (what's next).

```
CLAUDE.md            project context (read first)
docs/                progress log, data sources, architecture, next steps, setup
platform/            the Vercel app  ← deploy this subfolder
pipeline/            Python: enrichment loop, gov-data ingest, builders
source-data/         master inputs (rebuild platform/data from these; do not deploy)
```

Run locally: `cd platform && python3 -m http.server 8000`
Deploy: `cd platform && npx vercel --prod`
New here? `docs/SETUP_CLAUDE_CODE.md` is a plain-language first-30-minutes guide.
