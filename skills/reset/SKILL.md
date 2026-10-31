---
name: reset
description: Reset part or all of the user's data (profile, documents, jobs, applications, everything) after a zipped backup and typed confirmation.
---

# /reset (v1.0)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /reset.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run reset --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
