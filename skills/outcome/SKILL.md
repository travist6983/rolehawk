---
name: outcome
description: Record an application result and feedback, archive the documents sent, and draft a follow-up note in three tones.
---

# /outcome (v1.1)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /outcome.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run outcome --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
