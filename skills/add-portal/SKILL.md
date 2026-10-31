---
name: add-portal
description: Turn a job board URL into a portal plugin, preferring JSON APIs, RSS, or JSON-LD, and test-fetch sample jobs before enabling.
---

# /add-portal (v1.0)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /add-portal.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run add-portal --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
