---
name: add-template
description: Map an uploaded DOCX to CV template placeholders and produce a matching HTML twin for PDF output.
---

# /add-template (v1.1)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /add-template.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run add-template --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
