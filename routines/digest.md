---
schedule: "0 8 * * *"
reports: true
skills: [delivery]
credentials: []
timeout: 10m
---

Use the delivery skill to prepare the daily digest from changes.md.
Include up to five new verified findings, strongest first, with links, evidence, fit, unknowns, and a useful next step.
Include actual coverage and any source or screening failures; never invent activity counts or cost savings.
In coverage, report how many items Jev screened, how many qualified, and the Jev cost recorded in scan events; omit the cost if no event recorded it.
On a quiet day prepare a short coverage-only digest so the owner can see that the scout is running.
Retain any excess findings in your ledger for the next digest before consuming changes.
Use the delivery helper's prepare command and record the exact JSON envelope in a new Agent-owned delivery task.
Check for an existing envelope with the same run ID before creating another task.
In preview mode, print and record the digest instead of creating a delivery task.
Consume changes after recording the envelope or preview and any excess findings.
This routine never publishes; the separate deliver routine sends only envelopes already persisted by a successful preparation run.
Exclude delivery bookkeeping from digest content so sending a report does not generate another report.
