# Company watchlists

ATS sources (Greenhouse, Lever, Ashby, Workable) list jobs per company, not by keyword, so
/scrape walks a watchlist. Each CSV is the starter list for one ATS:

- `slug`: the company's board identifier in that ATS (for example, the part after
  `boards.greenhouse.io/`)
- `name`: display name
- `industry`: free-text industry tag, used by /setup to suggest companies
- `country`: ISO 3166-1 alpha-2 code for the company's main market, or `*`

Every row was checked live (a public board with open jobs) on 2026-10-31: Greenhouse 59,
Ashby 33, Lever 16, Workable 6. The app loads these into the `companies` table on start
(idempotent); users add or remove companies in the Sources screen, and removed starter rows
stay removed.

To grow or re-check the lists, from `backend/`:

```bash
uv run python scripts/verify_watchlist.py candidates.csv   # columns: ats,slug,name,industry,country
```

The script re-verifies existing rows too and drops boards that are gone or empty.
