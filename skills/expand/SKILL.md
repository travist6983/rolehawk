---
name: expand
description: Read public GitHub, portfolio, and course syllabi and propose new profile skills as accept/reject diffs.
---

# /expand (v2.0)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /expand.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run expand --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
