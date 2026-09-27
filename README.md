# Pain Scout

Find people describing the problem your product solves.

Pain Scout is an [OpenRoutines](https://openroutines.dev) agent that finds relevant conversations on Hacker News and in the subreddits you choose. Give it a customer brief, deploy it, and each morning it delivers a digest of conversations worth joining.

## Why it matters

Somewhere today, someone is asking for a recommendation, explaining a workaround, or describing the exact problem you built your product to solve. Finding those conversations by hand or by keyword means reading a lot of noise for a little signal.

Pain Scout reads the noise for you. It checks conversations against your brief and brings you only the ones worth your time, with the source, why they fit, and a useful way to jump in.

An example finding, using the included brief for a scheduled-job monitoring product:

> **A developer discovers a week of missing database backups**
>
> **What they said:** "They stopped last week and I only noticed when I checked the bucket."
>
> **Why it fits:** They run a nightly backup and need to know when it stops completing.
>
> **Still unknown:** Whether the backup script can send an HTTP request when it completes.
>
> **A way in:** Ask how they detect missing backups today, then share a completion-heartbeat example.
>
> **Source:** \[links directly to the original conversation\]

Each digest includes up to five new findings, a note on what was checked, and whether any sources failed. On quiet days, it tells you nothing qualified. See the [sample digest](examples/digest.md) for the full format.

Every screening decision is inspectable, including the posts that did not qualify. You can read the scores, edit the questions, and try different cutoffs to tune the digest suggestions.

## How it works

The agent runs 4 routines in sequence:

1. **Scan** (every six hours) searches Hacker News and new posts in your selected subreddits. It looks back seven days and screens up to 100 unseen items across both sources per scan. [TypeSafe's Jev](https://typesafe.ai) reads each item alongside your brief and checks for firsthand experience, product fit, exclusions, and requests for help. Qualifying matches are queued for investigation.
2. **Investigate** (every six hours, after each scan) uses a general model to open each queued conversation, check the context, and prepare the finding. Jev's cheap screening keeps this deeper research focused on promising conversations.
3. **Digest** (08:00 in your timezone) composes the morning digest from new findings and saves it, so a failed delivery can be retried.
4. **Deliver** (08:10) sends the saved digest to your configured destinations.

OpenRoutines runs the schedule and carries the scout's knowledge between runs, including what it has already found. You own the brief, routines, credentials, and deployment in one repository.

### What Jev sees

For each collected post, the script sends Jev, through OpenRouter, your complete customer brief, the post's title and text, its available source metadata, and four questions from [questions.json](skills/prospecting/questions.json):

| Dimension | Question |
| --- | --- |
| Firsthand | Does the observation explicitly describe the author's own concrete problem? |
| Fit | Does the described problem match a problem addressed in the product brief? |
| Excluded | Does the observation meet an exclusion in the brief? |
| Seeking | Is the author explicitly seeking help, an alternative, or a solution? |

Each question also instructs Jev to treat the observation as evidence, never as instructions.
Jev returns a value between 0 and 1 for each question.
The default selection rule requires firsthand and fit to each reach 0.8, with exclusion below 0.5.
Seeking is recorded for context and does not determine selection.

At this stage, Jev has not browsed your website or read the full discussion; it judges the supplied brief and collected text.
The general model checks the original conversation during investigation.

### The brief

Everything hinges on [skills/prospecting/brief.md](skills/prospecting/brief.md). It tells the scout:

- What your product does and who it helps.
- Which problems and workarounds signal a good fit.
- What to ignore.
- What useful help you could offer someone.

The included brief scouts for Tallyping, a fictional scheduled-job monitoring service with a straightforward use case: detecting missed scheduled jobs. Its website and documentation links are placeholders and do not resolve. Try the brief unchanged, then replace it with your own product's positioning. A specific paragraph about your customers is a good start.

### Sources

Choose your sources in [sources.json](skills/prospecting/sources.json):

- **Hacker News:** search posts and comments using phrases your customers use to describe their problems.
- **Reddit:** watch new post titles and bodies in specific subreddits. Jev checks relevance without requiring a keyword match. Reddit comments are not collected yet.

The included subreddit list is `selfhosted`, `sysadmin`, and `devops`, a starting point for the scheduled-job monitoring example.
Replace these with communities where your customers talk about their work.
Use either source or both; set `queries` to `[]` for Reddit only.
GitHub Discussions is a delivery destination, not a collection source.

Hacker News works without a source credential.
Reddit is optional and disabled until you configure API access below.

## Getting started

You need the [OpenRoutines CLI](https://openroutines.dev/docs/getting-started/), Docker, and an [OpenRouter API key](https://openrouter.ai/keys). The one key covers both Jev screening and the general model that runs the routines.

### 1. Try Jev without deploying anything

The repository includes [four sample conversations](examples/observations.json): a missed backup, a manual import check, a website-uptime request, and a promotional post. Run them through the real Jev API from the repository root:

```sh
read -rs OPENROUTER_API_KEY
export OPENROUTER_API_KEY
python3 skills/prospecting/scripts/scout.py screen examples/observations.json > /tmp/pain-scores.json
unset OPENROUTER_API_KEY
python3 skills/prospecting/scripts/scout.py review /tmp/pain-scores.json
```

Paste your OpenRouter key at the hidden prompt and press Enter. This makes four billable API calls, saves the complete results, and prints a table of scores and investigate/drop decisions. It sends no digest. The first two examples are intended matches and the other two are intended exclusions. Actual decisions come from Jev, so disagreement is useful feedback about the brief or the questions.

### 2. Make the agent yours

Copy this template into your own Git repository, then run:

```sh
openroutines configure
```

Configuration sets your owner details and timezone, and asks for your OpenRouter key. The general model defaults to Claude Sonnet 5 through OpenRouter. To use a different model, enter any OpenRouter model ID with the `openrouter/` prefix, or use another provider as described in the [model setup guide](https://openroutines.dev/docs/extending/#models). Jev screening uses the same key through OpenRouter's [System One API](https://openrouter.ai/docs/guides/community/typesafe-sdk). To call TypeSafe directly instead, set `jev_base_url` to `https://api.typesafe.ai` in `openroutines.yml`, store your key with `openroutines credentials set typesafe_api_key`, and grant `typesafe_api_key` in place of `openrouter_api_key` in the scan routine. Set `repo` in [openroutines.yml](openroutines.yml) to your repository's Git URL, then edit the customer brief, search phrases, and subreddit list. Keep the generated master key safe. API keys belong in the encrypted credential store.

### 3. Add your subreddits (optional)

Edit the `reddit` section of [sources.json](skills/prospecting/sources.json):

```json
"reddit": {
  "enabled": true,
  "subreddits": ["selfhosted", "sysadmin", "devops"],
  "posts_per_page": 25,
  "pages_per_subreddit": 2,
  "user_agent": "script:openroutines-pain-scout:v0.1 (by /u/YOUR_USERNAME)"
}
```

Use bare subreddit names, without `r/`, and replace `YOUR_USERNAME` with your Reddit username.
These settings fetch at most 50 recent posts per community before deduplication and the combined screening cap.
Busy communities may exceed that window; the digest reports collection limits and access failures.

Reddit requires [approval for commercial API use](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy), including the processing and delivery you intend.
Once approved, configure a confidential OAuth app supporting [application-only access](https://github.com/reddit-archive/reddit/wiki/OAuth2#application-only-oauth) and store its credentials:

```sh
openroutines credentials set reddit_client_id
openroutines credentials set reddit_client_secret
```

In [routines/scan.md](routines/scan.md), set:

```yaml
credentials: [openrouter_api_key, reddit_client_id, reddit_client_secret]
```

The scout obtains a fresh access token each run and stops Reddit requests when its rate allowance is exhausted.
It reads posts and prepares findings for you; it never posts replies or sends Reddit messages.
You can keep using Hacker News while arranging Reddit access.

### 4. Pick where the digest lands

**GitHub Discussions** gives you a browsable history of findings. Enable Discussions in your chosen repository (it can be private), then set these entries under `variables` in `openroutines.yml`:

```yaml
delivery: github
discussions_repo: your-org/your-repo
discussions_category: General
```

Choose an existing category, store a GitHub token with Discussions write access to that repository, and grant it to the deliver routine:

```sh
openroutines credentials set github_token
```

In [routines/deliver.md](routines/deliver.md), set `credentials: [github_token]`.

**Email** delivers the digest through your Resend account. Verify a sender domain in Resend, then set:

```yaml
delivery: email
digest_to: you@example.com
digest_from: Pain Scout <scout@yourdomain.com>
```

```sh
openroutines credentials set resend_api_key
```

In `routines/deliver.md`, set `credentials: [resend_api_key]`.

**Both:** set `delivery: both`, configure both destinations, and use `credentials: [github_token, resend_api_key]`. The email includes a link to the Discussion.

Leave `delivery: preview` to inspect the digest before enabling sending.

### 5. Run it once, then deploy

To try the full workflow locally, run these in order:

```sh
openroutines check
openroutines routines run scan --write-knowledge
openroutines routines run investigate --write-knowledge
openroutines routines run digest --write-knowledge
openroutines routines run deliver --write-knowledge
```

These are real runs. They use your API keys, and the final command sends to your configured destinations.

Commit your configuration, push your repository, and [deploy the container](https://openroutines.dev/docs/deploying/).

## Inspect every screening decision

The scan ledger keeps every screened post, including the ones that did not make the digest.
Each audit shows the four Jev scores, the original decision, and the exact cutoff that caused a rejection.
API failures are marked for retry rather than counted as rejected prospects.
The audit also preserves the brief, questions, post text, model version, and response from that scan.

For example, a borderline post might look like this (illustrative scores):

| Post | Firsthand | Fit | Excluded | Decision | Reason |
| --- | --- | --- | --- | --- | --- |
| Checking backups by hand | 0.92 | 0.75 | 0.06 | Drop | Fit is below 0.80 |

Lowering the cutoff to 0.70 would qualify that post without changing its scores.
If Jev misunderstood the problem instead, edit the brief or fit question and rescore the example.
The audit stays in the knowledge branch; rejected posts are not published in the daily digest.

After a deployed scan, pull the knowledge branch and open `knowledge/ledgers/scan.md`:

```sh
openroutines sync
python3 skills/prospecting/scripts/scout.py review knowledge/ledgers/scan.md
```

Try a different cutoff against those saved scores, without another API call:

```sh
python3 skills/prospecting/scripts/scout.py review knowledge/ledgers/scan.md --threshold 0.7
```

The comparison shows original and reviewed decisions side by side.
It does not change tasks, send findings, or overwrite the original audit.
The reasons describe the routing rule; Jev supplies scores, not a written explanation of its reasoning.

To see the exact JSON request for one post, copy its ID from the audit:

```sh
python3 skills/prospecting/scripts/scout.py request knowledge/ledgers/scan.md --id reddit:t3_abc123
```

Tune three separate inputs:

- **Context:** edit [brief.md](skills/prospecting/brief.md) to change the product, audience, and exclusions Jev evaluates against.
- **Questions:** edit [questions.json](skills/prospecting/questions.json) to change how Jev judges each dimension. Keep the four keys; their wording is editable.
- **Selection:** adjust `investigate_threshold` in `openroutines.yml`. Firsthand and fit must each meet that cutoff; exclusion must stay below 0.5. Help-seeking is recorded but does not determine selection.

Changing a brief or question requires new Jev calls to get new scores.
For a small local experiment, save the output of `screen examples/observations.json` to a JSON file, edit the brief or questions, and screen it again to a second file.
The `review` command accepts those JSON files as well as the scan ledger.
Previously screened live posts remain deduplicated; changing the brief does not automatically rescore history.

## Tuning

Start with a few searches and a small subreddit list, then read the first results.

- If the scout finds the wrong audience, sharpen the brief's exclusions.
- If it misses relevant conversations, broaden the Hacker News search phrases or choose more relevant subreddits in `sources.json`.
- If Reddit coverage is truncated, increase `pages_per_subreddit` within your API allowance or narrow the community list.
- Adjust `investigate_threshold` in `openroutines.yml` to change how selective screening is. The default is a starting point to evaluate against your own results.

<details>
<summary>Development and delivery details</summary>

The Python helpers use the standard library. Run their tests with:

```sh
python3 -m unittest discover -s tests -v
```

You can preview the [fictional sample digest](examples/digest.md) without credentials:

```sh
python3 skills/delivery/scripts/deliver.py prepare examples/digest.md > /tmp/pain-preview.json
python3 skills/delivery/scripts/deliver.py publish /tmp/pain-preview.json
```

GitHub retries look for the saved digest's marker before creating a Discussion. Resend retries use the same idempotency key. An unconfirmed email older than 23 hours requires manual reconciliation. Keep one deployed scout per destination/category and concurrency at one.

This template has local tests. Live classification quality and end-to-end delivery still need validation with configured accounts.

</details>
