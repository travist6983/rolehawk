---
name: rank
description: Score jobs 0-100 against the profile using SQL hard filters then batched LLM scoring, with must-have gaps and top reasons. Shows a cost estimate first.
---

# /rank (v1.0)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /rank.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run rank --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
