---
name: scrape
description: Fetch new jobs from enabled portals for active search targets, normalize, and dedupe. Reports found, new, duplicates, and errors per portal.
---

# /scrape (v1.0)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /scrape.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run scrape --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
