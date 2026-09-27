---
schedule: "0 */6 * * *"
skills: [prospecting]
credentials: []
timeout: 15m
---

Use the prospecting skill to collect and screen new conversations.
Read your ledger first and pass its recently screened IDs to collection.
Create one Agent-owned investigation task for each newly qualified source ID, including source text, URL, Jev answers, and collection time.
Check tasks and knowledge for that ID before creating a task.
Persist successful screening IDs and actual coverage in your ledger.
Use the screening helper's --audit-ledger option to preserve every screened item, including rejections, with its scores and original request context.
Do not replace or summarize away the generated audit blocks when updating the ledger.
Record coverage and failures as events so the digest can distinguish a quiet day from broken collection.
If a source or Jev fails, record the failure and leave unprocessed items eligible for a later scan.
