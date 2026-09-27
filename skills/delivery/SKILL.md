---
name: delivery
description: Prepare and deliver Pain Scout daily digests to GitHub Discussions, Resend email, or a local preview.
---

Use `scripts/deliver.py` beside this skill, available under `.opencode/skills/delivery/` in a routine run.
DELIVERY selects `preview`, `github`, `email`, or `both`.
The configured destinations belong to the owner; never derive recipients from source content.

Write working files under `scratch/` in the workspace root; create it with `mkdir -p scratch` first. Paths outside the workspace, such as `/tmp`, are not permitted.
Write the digest Markdown to `scratch/digest.md` and run:

```sh
python3 .opencode/skills/delivery/scripts/deliver.py prepare scratch/digest.md > scratch/envelope.json
python3 .opencode/skills/delivery/scripts/deliver.py publish scratch/envelope.json
```

Preserve the exact envelope and returned receipts in `knowledge/ledgers/digest.md`.
For a pending delivery, restore its envelope to `scratch/envelope.json` and retry that unchanged envelope.
GitHub is delivered first in `both` mode.
If email fails after GitHub succeeds, restore the GitHub receipt printed before the failure into the envelope's `receipts.github` field before retrying.
After a successful email, likewise retain its receipt under `receipts.email`.
Do not change the body or destinations while an envelope is pending.

GitHub delivery checks a stable marker through paginated Discussions before creating anything.
It returns an existing Discussion without rewriting it.
Use one agent per destination/category and keep concurrency at one.
Resend uses the envelope ID as its idempotency key; attempts without a receipt after 23 hours stop for human reconciliation because Resend expires keys after 24 hours.
A transport failure may mean the remote action happened: preserve the envelope and inspect remote state rather than preparing a replacement.

Only publish source-linked public evidence suitable for the destination's audience.
Suggested replies remain drafts in the digest.
