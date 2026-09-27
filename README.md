# Pain Scout

Find people describing the problem your product solves.

Pain Scout is an [OpenRoutines](https://openroutines.dev) agent built around [Jev](https://typesafe.ai), TypeSafe's structured decision model. Every six hours it collects conversations from Hacker News and Stack Exchange, and Jev scores each one against your product positioning for a fraction of a cent. The few that pass get a closer look from a general model, and each morning you get a digest of conversations worth joining.

## Why it matters

Somewhere today, someone is describing the exact problem your product solves. Keyword search can't tell that developer apart from a news story that happens to use the same words. A general model can, but reading every search result with one gets expensive fast.

Jev sits in between. It answers four yes-or-no questions about each post and returns a probability for each one. That makes it cheap enough to screen everything a loose search returns, so the scout spends real model time only on what qualifies. A test run with the included example looked like this:

| Step | Items | Reported cost |
| --- | --- | --- |
| Jev screening | 102 posts screened, 1 qualified | about $0.005 |
| Investigation with Claude Sonnet 5 | 1 post | about $0.19 |

Each finding in the digest looks like this:

> **A developer discovers a week of missing database backups**
>
> **What they said:** "They stopped last week and I only noticed when I checked the bucket."
>
> **Why it fits:** They run a nightly backup and need to know when it stops completing.
>
> **Still unknown:** Whether the backup script can send an HTTP request when it completes.
>
> **A way in:** Ask how they detect missing backups today, then share a completion-heartbeat example.

The scout prepares suggestions for you. It never contacts the people it finds. See the [sample digest](examples/digest.md) for the full format.

## How it works

Four routines run on a schedule:

1. **Scan** (every six hours) collects new posts from your sources, and Jev scores each one against your brief. It runs on Claude Haiku 4.5, since it only runs scripts and keeps records.
2. **Investigate** (every six hours, after each scan) has a general model open each qualifying conversation, check its context, and write the finding.
3. **Digest** (08:00 in your timezone) composes the morning digest, including what was scanned and what screening cost.
4. **Deliver** (08:10) sends the digest to GitHub Discussions, email, or both.

Jev answers these questions from [questions.json](skills/prospecting/questions.json) for every post:

| Question | Asks whether the post... |
| --- | --- |
| Firsthand | describes the author's own concrete problem |
| Fit | matches a problem your brief says you solve |
| Excluded | meets an exclusion in your brief |
| Seeking | asks for help, an alternative, or a solution |

A post qualifies when firsthand and fit both reach 0.8 and exclusion stays below 0.5. Seeking is recorded for context only. Every decision, including each rejection, is saved with its scores so you can review it later.

## Getting started

You need the [OpenRoutines CLI](https://openroutines.dev/docs/getting-started/), Docker, and an [OpenRouter API key](https://openrouter.ai/keys). One key covers Jev and the general models.

### 1. Try Jev on sample posts

The repository includes [four sample posts](examples/observations.json) for the example brief: two intended matches and two intended exclusions. Score them from the repository root:

```sh
read -rs OPENROUTER_API_KEY && export OPENROUTER_API_KEY
python3 skills/prospecting/scripts/scout.py screen examples/observations.json > /tmp/pain-scores.json
unset OPENROUTER_API_KEY
python3 skills/prospecting/scripts/scout.py review /tmp/pain-scores.json
```

Paste your key at the hidden prompt. This makes four billable Jev calls and prints each post's scores and decision.

### 2. Copy and configure the agent

Create your own repository from this template, clone it, and run:

```sh
openroutines configure
```

This sets your owner details and timezone and stores your OpenRouter key. Then set `repo` in [openroutines.yml](openroutines.yml) to your repository's Git URL.

### 3. Write your brief

Your company positioning goes in [skills/prospecting/brief.md](skills/prospecting/brief.md). Jev scores every post against this file, so it matters more than any other setting. It ships describing Tallyping, a fictional scheduled-job monitoring service. Replace each section with your own:

- **Product:** what your product does, in plain terms, with a link to your site and docs.
- **Ideal customer:** who has the problem, and what's true about their situation.
- **Problems we address:** the specific problems and workarounds you solve, one per bullet.
- **Strong signals:** what a good-fit post sounds like, such as a concrete incident or a manual workaround.
- **Exclusions:** what looks similar but isn't a fit, including problems you don't solve.
- **Helpful next step:** what useful help you could offer someone, so suggested replies stay helpful rather than salesy.

Specific beats polished. A plain paragraph about who your customers are and what goes wrong for them is a good start.

### 4. Choose where to look

Edit [skills/prospecting/sources.json](skills/prospecting/sources.json):

- **Hacker News `queries`:** phrases your customers use to describe the problem. Keep them loose, since Jev does the filtering.
- **Stack Exchange `sites` and `queries`:** sites where your customers ask questions, such as `serverfault` or `stackoverflow`, and short search terms. The search matches every word of a query.

Neither source needs a credential.

### 5. Pick where the digest lands

Set `delivery` under `variables` in `openroutines.yml`. Leave it as `preview` until you've seen a digest you like.

For **GitHub Discussions**, turn on Discussions in a repository, which can be private. Then set:

```yaml
delivery: github
discussions_repo: your-org/your-repo
discussions_category: General
```

For **email** through Resend, verify a sender domain, then set:

```yaml
delivery: email
digest_to: you@example.com
digest_from: Pain Scout <scout@yourdomain.com>
```

For **both**, set `delivery: both` and fill in both sets of values. Store the matching credentials and grant them in [routines/deliver.md](routines/deliver.md):

```sh
openroutines credentials set github_token    # Discussions write access
openroutines credentials set resend_api_key
```

```yaml
credentials: [github_token, resend_api_key]  # list only the ones you use
```

### 6. Run it, then deploy

Run each routine once. These are real runs that use your API keys, and the last one sends to your destinations unless `delivery` is `preview`.

```sh
openroutines check
openroutines routines run scan --write-knowledge
openroutines routines run investigate --write-knowledge
openroutines routines run digest --write-knowledge
openroutines routines run deliver --write-knowledge
```

Then commit, push, and [deploy the container](https://openroutines.dev/docs/deploying/).

## Tune the results

Every scan saves its scores in the scan ledger on the knowledge branch. Pull it and review the decisions:

```sh
openroutines sync
python3 skills/prospecting/scripts/scout.py review knowledge/ledgers/scan.md
```

Replay a different cutoff against the saved scores, with no new API calls:

```sh
python3 skills/prospecting/scripts/scout.py review knowledge/ledgers/scan.md --threshold 0.7
```

Then adjust what caused the miss:

- **Wrong audience or problem:** sharpen the brief, especially its exclusions.
- **Too strict or too loose:** change `investigate_threshold` in `openroutines.yml`.
- **Misjudged dimension:** reword that question in `questions.json`. Keep the four keys.
- **Missing conversations:** broaden the search phrases or add Stack Exchange sites.

Changing the brief or questions affects new scans only. Posts already screened aren't rescored.

<details>
<summary>Advanced setup</summary>

**Models.** The general model defaults to Claude Sonnet 5 through OpenRouter. You can pick another OpenRouter model during `openroutines configure`, or use another provider as described in the [model setup guide](https://openroutines.dev/docs/extending/#models). The scan routine sets its own model in [routines/scan.md](routines/scan.md), so change that line too if you switch. With a non-OpenRouter default model, grant `openrouter_api_key` in the scan routine so Jev screening can still use it.

**Calling TypeSafe directly.** Jev runs through OpenRouter's [System One API](https://openrouter.ai/docs/guides/community/typesafe-sdk) by default. To use TypeSafe's API instead, set `jev_base_url` to `https://api.typesafe.ai`, store your key with `openroutines credentials set typesafe_api_key`, and grant it in the scan routine.

**Stack Exchange quota.** Stack Exchange allows 300 requests a day per IP address without a key, and the defaults use 9 per scan. For more, [register an app](https://stackapps.com/apps/oauth/register) and set `stackexchange_key` in `openroutines.yml`. The key isn't secret, so it's a variable. Stack Exchange content is licensed CC BY-SA, and every finding links to its source.

**Inspecting one request.** To see the exact JSON sent to Jev for one post, pass its ID from the audit:

```sh
python3 skills/prospecting/scripts/scout.py request knowledge/ledgers/scan.md --id stackexchange:serverfault:123456
```

**Delivery retries.** GitHub retries look for the saved digest's marker before creating a Discussion. Resend retries reuse the same idempotency key, and an unconfirmed email older than 23 hours needs manual reconciliation. Keep one deployed scout per destination and concurrency at one.

**Tests.** The Python helpers use only the standard library:

```sh
python3 -m unittest discover -s tests -v
```

</details>
