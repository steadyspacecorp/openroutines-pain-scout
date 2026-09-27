---
schedule: "30 */6 * * *"
skills: [prospecting]
webfetch: true
timeout: 20m
---

Read the prospecting brief and process at most MAX_INVESTIGATIONS open investigation tasks, oldest first.
Verify each original conversation and the product capability relevant to it.
Close unsupported matches with a specific reason.
For each useful match, record an event and a Human-owned task containing the source ID, linked conversation, a short evidence excerpt, why it fits, what remains unknown, and a suggested helpful response.
These are suggestions for the owner, not permission to contact anyone.
Complete the investigation task only after recording its result.
Do not create a second finding for an ID already recorded.
When source access fails, leave the task open with the obstacle instead of inventing evidence.
