---
name: setup
description: Build or update the candidate profile from a resume, CV text, or LinkedIn export, then run a one-question-at-a-time gap interview. Writes profile.md, preferences.md, and search targets.
---

# /setup (v1.0)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /setup.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run setup --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
