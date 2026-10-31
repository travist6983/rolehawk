---
name: upskill
description: Compare top ranked jobs' requirements to the profile and output a gap table and a 4-8 week learning plan.
---

# /upskill (v2.0)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /upskill.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run upskill --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
