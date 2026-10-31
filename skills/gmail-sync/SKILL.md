---
name: gmail-sync
description: Read recent application emails over IMAP, classify them, and propose stage changes for the user to approve. Never sends mail.
---

# /gmail-sync (v1.1)

> Stub. Implemented in a later chunk; see `docs/SPEC.md` "Command specs" for /gmail-sync.

Run against the user's Offerbound data folder (`~/Offerbound`, or `OFFERBOUND_HOME`):

```bash
offerbound run gmail-sync --json
```

This skill is a thin caller. All logic lives in the backend service layer, so the result matches the dashboard and chat drawer exactly.
