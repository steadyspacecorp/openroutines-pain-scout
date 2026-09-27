from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scout = load("scout", "skills/prospecting/scripts/scout.py")
delivery = load("delivery", "skills/delivery/scripts/deliver.py")


class ScreeningTests(unittest.TestCase):
    def answers(self, **overrides):
        values = dict(firsthand=0.9, fit=0.9, excluded=0.1, seeking=0.2)
        values.update(overrides)
        return {k: {"type": "noul", "noul": v} for k, v in values.items()}

    def test_exclusion_overrides_fit(self):
        self.assertEqual(scout.route(self.answers(excluded=0.8), 0.8), "drop")
        self.assertEqual(scout.route(self.answers(), 0.8), "investigate")

    def test_malformed_answers_fail_closed(self):
        for value in [float("nan"), 1.1, True, "0.9"]:
            with self.assertRaises(ValueError):
                scout.route(self.answers(fit=value), 0.8)

    def test_collection_deduplicates_and_reports_limits(self):
        def fetch(url):
            return {"hits": [{"objectID": "1", "comment_text": "old"},
                             {"objectID": "2", "comment_text": "<p>new &amp; useful</p>"},
                             {"objectID": "3", "comment_text": "also new"}], "nbPages": 2}
        result = scout.collect({"queries": ["one", "two"], "lookback_hours": 24,
                                "pages_per_query": 1, "max_items": 1}, {"1"}, fetch, 100000)
        self.assertEqual(len(result["observations"]), 1)
        self.assertEqual(result["observations"][0]["text"], "new & useful")
        self.assertEqual(result["coverage"]["deferred_by_cap"], 1)
        self.assertEqual(len(result["coverage"]["truncated_queries"]), 2)

    @patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"})
    def test_failed_screen_is_retryable(self):
        result = scout.screen({"observations": [{"id": "1"}], "coverage": {}}, "brief", 0.8,
                              lambda *args: {"answers": {}})
        self.assertEqual(result["results"][0]["route"], "retry")


class DeliveryTests(unittest.TestCase):
    @patch.dict(os.environ, {"DELIVERY": "both", "OPENROUTINES_RUN_ID": "stable-run"})
    def envelope(self):
        result = delivery.prepare("body")
        result.update(repo="owner/repo", category="General", to="to@example.com", **{"from": "from@example.com"})
        return result

    def test_partial_delivery_does_not_repeat_github(self):
        envelope = self.envelope()
        calls = []
        def github(e):
            calls.append("github")
            return {"id": "D1", "url": "https://github.com/owner/repo/discussions/1"}
        def fail(e):
            raise TimeoutError()
        with self.assertRaises(TimeoutError):
            delivery.publish(envelope, github, fail, lambda *a, **k: None)
        delivery.publish(envelope, github, lambda e: {"id": "E1"}, lambda *a, **k: None)
        self.assertEqual(calls, ["github"])
        self.assertIn("email", envelope["receipts"])

    def test_existing_discussion_on_later_page_is_reused(self):
        envelope = self.envelope()
        calls = []
        def gql(query, variables):
            calls.append(query)
            self.assertNotIn("mutation", query)
            if "discussionCategories" in query:
                return {"repository": {"id": "R1", "discussionCategories": {"nodes": [{"id": "C1", "name": "General"}]}}}
            if not variables["cursor"]:
                return {"repository": {"discussions": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "next"}}}}
            return {"repository": {"discussions": {"nodes": [{"id": "D1", "url": "url", "body": "<!-- pain-scout:" + envelope["id"] + " -->"}], "pageInfo": {"hasNextPage": False}}}}
        self.assertEqual(delivery.discussion(envelope, gql)["id"], "D1")
        self.assertEqual(len(calls), 3)

    def test_expired_email_never_sends(self):
        envelope = self.envelope()
        envelope["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        with self.assertRaises(ValueError):
            delivery.email(envelope, lambda *args: self.fail("must not send"))

    @patch.dict(os.environ, {"RESEND_API_KEY": "test"})
    def test_email_uses_stable_key_and_discussion_link(self):
        envelope = self.envelope()
        envelope["receipts"]["github"] = {"id": "D1", "url": "https://github.com/owner/repo/discussions/1"}
        def post(url, payload, token, headers):
            self.assertEqual(headers["Idempotency-Key"], "pain-scout/" + envelope["id"])
            self.assertIn(envelope["receipts"]["github"]["url"], payload["text"])
            self.assertEqual(payload["to"], ["to@example.com"])
            return {"id": "E1"}
        self.assertEqual(delivery.email(envelope, post)["id"], "E1")


if __name__ == "__main__":
    unittest.main()
