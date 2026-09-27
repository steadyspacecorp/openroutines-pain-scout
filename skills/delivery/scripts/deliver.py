import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(url, payload, token, extra=None):
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json",
               "User-Agent": "OpenRoutines-Pain-Scout"}
    headers.update(extra or {})
    with urlopen(Request(url, data=json.dumps(payload).encode(), headers=headers), timeout=30) as response:
        return json.load(response)


def graphql(query, variables):
    result = request("https://api.github.com/graphql", {"query": query, "variables": variables}, os.environ["GITHUB_TOKEN"])
    if result.get("errors"):
        raise ValueError("GitHub rejected the operation; inspect permissions and repository settings")
    return result["data"]


def prepare(body, now=None):
    now = now or datetime.now(timezone.utc)
    mode = os.environ.get("DELIVERY", "preview")
    if mode not in ("preview", "github", "email", "both"):
        raise ValueError("invalid delivery mode")
    run = os.environ.get("OPENROUTINES_RUN_ID", "")
    if mode != "preview" and not run:
        raise ValueError("live delivery requires an OpenRoutines run ID")
    return {"id": hashlib.sha256((run or body).encode()).hexdigest(),
            "created_at": now.isoformat(), "title": "Pain Scout · " + now.date().isoformat(),
            "body": body, "mode": mode, "repo": os.environ.get("DISCUSSIONS_REPO", ""),
            "category": os.environ.get("DISCUSSIONS_CATEGORY", "General"),
            "to": os.environ.get("DIGEST_TO", ""), "from": os.environ.get("DIGEST_FROM", ""),
            "receipts": {}}


def discussion(envelope, gql=graphql):
    owner, name = envelope["repo"].split("/")
    marker = "<!-- pain-scout:" + envelope["id"] + " -->"
    metadata = gql("""query($owner:String!,$name:String!){repository(owner:$owner,name:$name){
      id discussionCategories(first:100){nodes{id name}}}}""", {"owner": owner, "name": name})["repository"]
    category = next(c["id"] for c in metadata["discussionCategories"]["nodes"] if c["name"] == envelope["category"])
    cursor = None
    while True:
        page = gql("""query($owner:String!,$name:String!,$category:ID!,$cursor:String){
          repository(owner:$owner,name:$name){discussions(first:100,categoryId:$category,after:$cursor){
            nodes{id url body} pageInfo{hasNextPage endCursor}}}}""",
                   {"owner": owner, "name": name, "category": category, "cursor": cursor})["repository"]["discussions"]
        for node in page["nodes"]:
            if marker in node["body"]:
                return {"id": node["id"], "url": node["url"]}
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return gql("""mutation($input:CreateDiscussionInput!){createDiscussion(input:$input){discussion{id url}}}""",
               {"input": {"repositoryId": metadata["id"], "categoryId": category,
                          "title": envelope["title"], "body": envelope["body"] + "\n\n" + marker}})["createDiscussion"]["discussion"]


def email(envelope, post=request, now=None):
    now = now or datetime.now(timezone.utc)
    age = (now - datetime.fromisoformat(envelope["created_at"])).total_seconds()
    if age < 0 or age >= 23 * 3600:
        raise ValueError("email envelope is outside the safe retry window; reconcile in Resend")
    if not envelope["to"] or not envelope["from"]:
        raise ValueError("email sender and recipient are required")
    body = envelope["body"]
    if envelope["receipts"].get("github"):
        body += "\n\nDiscussion: " + envelope["receipts"]["github"]["url"]
    return post("https://api.resend.com/emails", {"from": envelope["from"], "to": [envelope["to"]],
                "subject": envelope["title"], "text": body}, os.environ["RESEND_API_KEY"],
                {"Idempotency-Key": "pain-scout/" + envelope["id"]})


def publish(envelope, github_send=discussion, email_send=email, emit=print):
    mode = envelope["mode"]
    if mode not in ("preview", "github", "email", "both"):
        raise ValueError("invalid delivery mode")
    if mode == "preview":
        emit(json.dumps(envelope, indent=2))
        return
    for channel, send, enabled in [("github", github_send, mode in ("github", "both")),
                                   ("email", email_send, mode in ("email", "both"))]:
        if enabled and channel not in envelope["receipts"]:
            receipt = send(envelope)
            if not receipt.get("id"):
                raise ValueError("delivery response has no receipt")
            envelope["receipts"][channel] = receipt
            emit(json.dumps({"channel": channel, "receipt": receipt}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "publish"])
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(args.input.read_text()), indent=2))
    else:
        publish(json.loads(args.input.read_text()))


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError, OSError, StopIteration, TypeError):
        sys.exit("Delivery incomplete. Preserve envelope and printed receipts; check configuration and provider before retrying.")
