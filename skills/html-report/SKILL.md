---
name: html-report
description: Export one self-contained HTML report of the application pipeline, with no network requests.
---

# /html-report (v1.0)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /html-report.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run html-report --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
