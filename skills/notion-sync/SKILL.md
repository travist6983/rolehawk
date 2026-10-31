---
name: notion-sync
description: Publish a read-only pipeline database to Notion via an integration token.
---

# /notion-sync (v2.0)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /notion-sync.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run notion-sync --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
