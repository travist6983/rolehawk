---
name: apply
description: Fit-check a job, draft a tailored CV and cover letter that never invent profile facts, review them for truthfulness, and render DOCX and PDF.
---

# /apply (v1.0)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /apply.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run apply --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
