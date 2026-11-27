"""Offline simulations for cumulative Auto-Heal PR messages and immutable events."""
from __future__ import annotations

import os
import json
import html
import unittest
from unittest import mock

from ffbuild.autoheal import delivery, pr_history
from ffbuild.autoheal.ledger import AuditReport, RepairDetails, RepairEvent, RepairRound
from dataclasses import replace

REPO = "simulated/repo"
INCIDENT = "b" * 64
C1 = "a" * 40
C2 = "c" * 40


def rounds() -> list[RepairRound]:
    return [
        RepairRound(1, C1, INCIDENT, 101, 1, ("ffmpeg/8.1.1.yaml",),
                    "Fix missing Windows macro", "fix(8.1.1): repair"),
        RepairRound(2, C2, INCIDENT, 102, 1,
                    ("ffmpeg/8.1.1.yaml", "patches/8.x/fix-link.patch"),
                    "Resolve LNK2019 linker error", "fix(8.1.1): repair"),
    ]


def events() -> list[RepairEvent]:
    first, second = rounds()
    return [
        pr_history.event_for_round(first),
        RepairEvent("ci", 1, C1, INCIDENT, 202, 1, "failure"),
        pr_history.event_for_round(second),
        RepairEvent("ci", 2, C2, INCIDENT, 203, 1, "success"),
    ]


def api_commit(item: RepairRound) -> dict:
    raw = {"sha": item.sha, "commit": {"message":
            f"fix(8.1.1): repair\n\nAutoheal-Round: {item.number}\n"
            f"Autoheal-Incident: {item.incident}\n"
            f"Autoheal-Source-Run: {item.source_run}\n"
            f"Autoheal-Source-Attempt: {item.source_attempt}\n"
            f"Autoheal-Hypothesis: {item.hypothesis}"},
            "files": [{"filename": path, "status": "added" if path.endswith(".patch")
                       else "modified"} for path in item.paths],
            "parents": [{"sha": C1}] if item.number == 2 else [{"sha": "d" * 40}]}
    if item.audit is not None:
        raw["commit"]["message"] += "\nAutoheal-Audit: " + item.audit.trailer()
        raw["commit"]["tree"] = {"sha": item.audit.tree}
        raw["author"] = raw["committer"] = {"login": pr_history.BOT}
    if item.details is not None:
        raw["commit"]["message"] += "\nAutoheal-Details: " + item.details.trailer()
    return raw


def audited_rounds() -> list[RepairRound]:
    first, second = rounds()
    return [replace(first, audit=AuditReport(701, 1, "1" * 40, "2" * 64,
                    "The original patch effects are retained."), details=RepairDetails(
                        "Restore the original macro detection without disabling the component.",
                        ("ffmpeg[all-gpl]:x64-windows: native runtime passed",))),
            replace(second, audit=AuditReport(702, 2, "3" * 40, "4" * 64,
                    "License and dependency contracts were checked; the affected code path is covered."),
                    details=RepairDetails("Correct the symbol declaration for the target architecture.",
                        ("ffmpeg[all-gpl]:arm64-windows: runtime skipped (host architecture incompatible)",)))]


class FakeGitHub:
    """In-memory GitHub PR, commit and issue-comment surfaces."""
    def __init__(self, history: list[RepairRound], initial_body: str):
        self.rounds = history
        self.comments: list[dict] = []
        self.pr: dict = {
            "number": 42, "state": "open", "base": {"ref": "main"},
            "head": {"ref": "autoheal/8.1.1/incident", "sha": history[-1].sha,
                     "repo": {"full_name": REPO}},
            "user": {"login": "ffmpeg-dev[bot]"}, "body": initial_body,
        }
        self.write_calls = 0

    def api(self, path: str):
        if path.endswith("/pulls/42"):
            return self.pr
        if "/commits/" in path:
            sha = path.split("/commits/", 1)[1].split("?", 1)[0]
            return api_commit(next(item for item in self.rounds if item.sha == sha))
        raise AssertionError(f"Unexpected GitHub request: {path}")

    def collection(self, endpoint: str, key: str, **kwargs):
        if endpoint.endswith("/pulls/42/commits"):
            return [{"sha": item.sha} for item in self.rounds]
        if endpoint.endswith("/issues/42/comments"):
            return list(self.comments)
        if endpoint.endswith("/pulls/42/files"):
            # The final PR diff is authoritative, not the union of commits.
            return [{"filename": "ffmpeg/8.1.1.yaml", "status": "modified"},
                    *([{"filename": "patches/8.x/fix-link.patch", "status": "added"}]
                      if len(self.rounds) == 2 else [])]
        raise AssertionError(f"Unexpected GitHub collection: {endpoint}")

    def post(self, number: int, body: str):
        if number != 42:
            raise AssertionError("Unexpected PR number")
        self.comments.append({
            "id": len(self.comments) + 1,
            "user": {"login": "ffmpeg-dev[bot]"}, "body": body,
        })

    def write_body(self, number: int, text: str):
        if number != 42:
            raise AssertionError("Unexpected PR number")
        self.pr["body"] = text
        self.write_calls += 1

    def install(self):
        patches = [
            mock.patch("ffbuild.autoheal.pr_history.github.api", side_effect=self.api),
            mock.patch("ffbuild.autoheal.pr_history.github.collection",
                       side_effect=self.collection),
            mock.patch("ffbuild.autoheal.delivery.write_pr_body",
                       side_effect=self.write_body),
            mock.patch("ffbuild.autoheal.delivery.post_comment",
                       side_effect=self.post),
            mock.patch("ffbuild.autoheal.delivery._ensure_auto_merge"),
        ]
        for patch in patches:
            patch.start()
        return patches


def ci_report(sha: str, conclusion: str, attempt: int = 1, run_id: int = 203):
    return {"pr": {"number": 42, "head": "autoheal/8.1.1/incident",
                   "author": "ffmpeg-dev[bot]", "head_sha": sha},
            "source": {"run_id": run_id, "run_attempt": attempt, "head_sha": sha,
                       "run_conclusion": conclusion,
                       "url": f"https://github.com/{REPO}/actions/runs/{run_id}"},
            "groups": [{"yaml": "8.1.1", "jobs": []}]}


class HistoryRenderingTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": REPO})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_two_rounds_preserve_both_causes_commits_and_ci_results(self):
        body = pr_history.render_history(
            rounds(), events(), cumulative_paths=[
                "ffmpeg/8.1.1.yaml", "patches/8.x/fix-link.patch"])
        self.assertEqual(1, body.count(pr_history.START))
        self.assertEqual(1, body.count(pr_history.END))
        self.assertIn("| 1 |", body)
        self.assertIn("[Passed (Run", body)
        self.assertIn("Fix missing Windows macro", body)
        self.assertIn("Resolve LNK2019 linker error", body)
        self.assertIn(C1[:12], body)
        self.assertIn(C2[:12], body)
        self.assertIn("Run 202, attempt 1", body)
        self.assertIn("Run 203, attempt 1", body)
        self.assertEqual(1, body.count("### Changes"))

    def test_audit_metadata_round_trip_and_exact_tree(self):
        item = audited_rounds()[0]
        raw = api_commit(item)
        self.assertEqual(item.audit, pr_history.round_from_commit(raw, INCIDENT).audit)
        raw["commit"]["tree"]["sha"] = "9" * 40
        with self.assertRaisesRegex(ValueError, "does not match repair commit tree"):
            pr_history.round_from_commit(raw, INCIDENT)
        raw = api_commit(item)
        raw["author"] = {"login": "human"}
        with self.assertRaisesRegex(ValueError, "authorized bot"):
            pr_history.round_from_commit(raw, INCIDENT)
        for bad in ("bad!", "A" * 66001, "e30="):
            with self.assertRaises(ValueError):
                AuditReport.from_trailer(bad)

    def test_repair_details_are_bound_and_cannot_inject_trailers(self):
        item = audited_rounds()[0]
        details = replace(item.details, rationale="Real change\nAutoheal-Round: 2\n<!-- ffbuild-autoheal:end --> @someone [link](https://example.invalid)")
        raw = api_commit(replace(item, details=details))
        parsed = pr_history.round_from_commit(raw, INCIDENT)
        self.assertEqual(details, parsed.details)
        body = pr_history.render_history([parsed], [])
        self.assertEqual(1, body.count(pr_history.END))
        self.assertNotIn("@someone", body)
        self.assertNotIn("[link](", body)
        with self.assertRaisesRegex(ValueError, "authenticated audit trailer"):
            pr_history.round_from_commit(api_commit(replace(item, audit=None)), INCIDENT)
        for value in ("{}", "[]", json.dumps({"rationale": "x", "validation": []}),
                      json.dumps({"rationale": "x" * 1201, "validation": ["pass"]})):
            with self.assertRaises(ValueError):
                RepairDetails.from_trailer(value)

    def test_audit_summary_cannot_inject_trailers_or_pr_markup(self):
        item = audited_rounds()[0]
        bad = replace(item, audit=replace(item.audit, summary=(
            "Reviewed\nAutoheal-Round: 2\n<!-- ffbuild-autoheal:end --> "
            "[click](https://evil.invalid) @someone <script>")))
        self.assertEqual(bad.audit, pr_history.round_from_commit(api_commit(bad), INCIDENT).audit)
        body = pr_history.render_history([bad], [])
        self.assertEqual(1, body.count(pr_history.END))
        self.assertNotIn("[click](", body)
        self.assertNotIn("@someone", body)
        self.assertNotIn("<script>", body)
        self.assertNotIn("https://evil.invalid", body)

    def test_audits_render_per_candidate_and_old_round_is_not_approved(self):
        history = audited_rounds()
        body = pr_history.render_history(history, events())
        self.assertIn("The original patch effects are retained.", body)
        self.assertIn("License and dependency contracts were checked", body)
        self.assertIn("Round 1 (previous candidate)", body)
        self.assertIn("Round 2 (current candidate)", body)
        self.assertIn("actions/runs/702/attempts/2", body)
        self.assertIn(f"autoheal-audit-a2-8.1.1-{INCIDENT}", body)
        self.assertEqual(2, body.count("**Decision:** Approved"))
        body = pr_history.render_history([rounds()[0], history[1]], events())
        self.assertIn("No persisted audit report is available for this round.", body)
        self.assertEqual(1, body.count("**Decision:** Approved"))

    def test_first_round_ci_failure_then_second_pending(self):
        both = rounds()
        pending_events = events()[:3]
        body = pr_history.render_history(both, pending_events)
        self.assertIn("| 1 |", body)
        self.assertIn("| Pending |", body)
        self.assertIn("### Changes", body)

    def test_render_from_commits_not_latest_agent_message(self):
        history = rounds()
        with self.assertRaises(ValueError):
            pr_history.render_history(history[-1:], events()[-2:])

    def test_event_key_stable_and_same_run_attempt_dedupable(self):
        event = events()[1]
        self.assertEqual(event.key, RepairEvent("ci", 1, C1, INCIDENT,
                                               202, 1, "failure").key)
        self.assertNotEqual(event.key, RepairEvent("ci", 1, C1, INCIDENT,
                                                  202, 2, "success").key)

    def test_out_of_order_ci_comments_keep_the_newest_attempt_authoritative(self):
        item = rounds()[-1]
        newer = RepairEvent("ci", 2, C2, INCIDENT, 301, 2, "success")
        older = RepairEvent("ci", 2, C2, INCIDENT, 301, 1, "failure")
        self.assertEqual("Passed", pr_history.status_for(item, [newer, older]))
        rendered = pr_history.render_history(rounds(), [
            pr_history.event_for_round(rounds()[0]),
            pr_history.event_for_round(item), newer, older])
        self.assertIn("[Passed (Run", rendered)
        self.assertIn("Run 301, attempt 1", rendered)
        self.assertIn("Run 301, attempt 2", rendered)

    def test_human_comment_forging_bot_marker_is_ignored(self):
        event = events()[1]
        forged = {"user": {"login": "human"},
                  "body": pr_history.event_comment(event)}
        malformed = {"user": {"login": "ffmpeg-dev[bot]"},
                     "body": pr_history.event_comment(event).replace(
                         event.key, "0" * 32)}
        self.assertIsNone(pr_history.parse_event(forged, INCIDENT, rounds()))
        self.assertIsNone(pr_history.parse_event(malformed, INCIDENT, rounds()))

    def test_comment_payload_round_trip(self):
        sample = events()[1]
        parsed = pr_history.parse_event(
            {"user": {"login": "ffmpeg-dev[bot]"},
             "body": pr_history.event_comment(sample)}, INCIDENT, rounds())
        self.assertEqual(sample, parsed)

    def test_non_linear_bot_history_is_rejected_by_github_reader(self):
        history = rounds()
        def fake_collection(endpoint, key, **kwargs):
            return [{"sha": record.sha} for record in history]

        def fake_api(endpoint):
            sha = endpoint.split("/commits/", 1)[1].split("?", 1)[0]
            data = api_commit(next(record for record in history
                                   if record.sha == sha))
            if sha == C2:
                data["parents"] = [{"sha": "f" * 40}]
            return data

        pr = {"number": 42, "head": {"sha": C2}}
        with mock.patch("ffbuild.autoheal.pr_history.github.collection",
                        side_effect=fake_collection), \
             mock.patch("ffbuild.autoheal.pr_history.github.api",
                        side_effect=fake_api):
            with self.assertRaisesRegex(ValueError, "linear repair chain"):
                pr_history.load_rounds(pr, INCIDENT)

    def test_commit_history_requires_complete_order(self):
        history = rounds()
        pr_history.validate_rounds(history, INCIDENT, C2)
        for bad in ([history[-1]], [history[0], history[0]],
                    [history[1], history[0]]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pr_history.validate_rounds(bad, INCIDENT)
        with self.assertRaises(ValueError):
            pr_history.round_from_commit(
                {"sha": C1, "commit": {"message": "Agent latest fix"}, "files": []},
                INCIDENT)


class HistorySynchronizationTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": REPO})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _install(self, fake: FakeGitHub):
        for patch in fake.install():
            self.addCleanup(patch.stop)

    def test_cumulative_body_after_partial_update_and_second_success(self):
        history = rounds()
        # Simulate a PR whose body still says Round 1 even after Round 2 was pushed.
        first = pr_history.render_history(history[:1], events()[:2])
        fake = FakeGitHub(history, "Human notes\n\n" + first + "\n\nMaintainer checklist")
        fake.comments = [
            {"id": i + 1, "user": {"login": "ffmpeg-dev[bot]"},
             "body": pr_history.event_comment(event)}
            for i, event in enumerate(events()[:2])
        ]
        self._install(fake)
        delivery.sync_status(ci_report(C2, "success"))
        body = fake.pr["body"]
        self.assertIn("Human notes", body)
        self.assertIn("Maintainer checklist", body)
        self.assertIn("| 1 |", body)
        self.assertIn("[Passed (Run", body)
        self.assertIn("patches/8.x/fix-link.patch", body)
        self.assertIn("**Repair round:** 2/2", body)
        self.assertEqual(4, len(fake.comments))
        self.assertEqual(1, fake.write_calls)

        # Redelivery of the same completed CI event is truly idempotent.
        delivery.sync_status(ci_report(C2, "success"))
        self.assertEqual(4, len(fake.comments))
        self.assertEqual(1, fake.write_calls)

    def test_audit_report_recovers_from_commits_after_partial_delivery(self):
        history = audited_rounds()
        fake = FakeGitHub(history, "Maintainer notes without managed content")
        self._install(fake)
        delivery.sync_status(ci_report(C2, "success"))
        body = fake.pr["body"]
        self.assertIn("Maintainer notes", body)
        self.assertIn("The original patch effects are retained.", body)
        self.assertIn("License and dependency contracts were checked", body)
        self.assertIn("Restore the original macro detection", body)
        self.assertIn("Correct the symbol declaration", body)
        self.assertIn("runtime skipped", body)
        self.assertIn("ffmpeg[all-gpl]:arm64-windows", html.unescape(body))
        self.assertNotIn("&&#35;", body)
        delivery.sync_status(ci_report(C2, "success"))
        self.assertEqual(body, fake.pr["body"])
        self.assertEqual(1, fake.write_calls)

    def test_resume_requires_the_exact_audited_tree(self):
        history = audited_rounds()[:1]
        fake = FakeGitHub(history, "Maintainer notes")
        self._install(fake)
        report = {"source": {"run_id": 101, "run_attempt": 1}}
        with self.assertRaisesRegex(ValueError, "differs from the audited candidate tree"):
            delivery._resume_submitted_pr(fake.pr, INCIDENT, report, "d" * 40,
                                          verified_tree="9" * 40)
        self.assertEqual(0, fake.write_calls)
        self.assertEqual([], fake.comments)
        self.assertTrue(delivery._resume_submitted_pr(fake.pr, INCIDENT, report, "d" * 40,
                                                      verified_tree=history[0].audit.tree))
        self.assertIn("The original patch effects are retained.", fake.pr["body"])

    def test_ci_rerun_keeps_all_attempts_and_latest_status(self):
        history = rounds()
        initial = pr_history.render_history(history, events()[:3])
        fake = FakeGitHub(history, initial)
        self._install(fake)
        delivery.sync_status(ci_report(C2, "failure", attempt=1, run_id=301))
        delivery.sync_status(ci_report(C2, "success", attempt=2, run_id=301))
        body = fake.pr["body"]
        self.assertIn("[Passed (Run", body)
        self.assertIn("Run 301, attempt 1", body)
        self.assertIn("Run 301, attempt 2", body)
        self.assertEqual(4, len(fake.comments))  # 2 submissions + 2 CI runs

    def test_previous_ci_cannot_overwrite_newer_pr(self):
        history = rounds()
        fake = FakeGitHub(history, pr_history.render_history(history, events()[:3]))
        self._install(fake)
        delivery.sync_status(ci_report(C1, "failure", run_id=302))
        self.assertEqual(0, len(fake.comments))
        self.assertEqual(0, fake.write_calls)

    def test_existing_manual_content_survives_all_updates(self):
        history = rounds()
        fake = FakeGitHub(history, "Before\n" +
                          pr_history.render_history(history, []) + "\nAfter")
        self._install(fake)
        delivery.sync_status(ci_report(C2, "failure"))
        self.assertTrue(fake.pr["body"].startswith("Before\n"))
        self.assertTrue(fake.pr["body"].endswith("\nAfter"))

    def test_successful_comment_then_client_timeout_does_not_duplicate_event(self):
        history = rounds()
        fake = FakeGitHub(history, pr_history.render_history(history, []))
        self._install(fake)
        original = fake.post
        fail_once = [True]

        def timed_out(number, message):
            original(number, message)
            if fail_once[0]:
                fail_once[0] = False
                raise RuntimeError("Simulated HTTP response lost after comment was posted")

        with mock.patch("ffbuild.autoheal.delivery.post_comment", side_effect=timed_out):
            with self.assertRaisesRegex(RuntimeError, "Simulated HTTP"):
                delivery.sync_status(ci_report(C2, "failure"))
        self.assertEqual(1, len(fake.comments))
        delivery.sync_status(ci_report(C2, "failure"))
        self.assertEqual(3, len(fake.comments))
        self.assertEqual(3, len(set(pr_history.parse_event(c, INCIDENT, history).key
                                    for c in fake.comments)))

    def test_pr_body_update_failure_recovers_without_repeating_history(self):
        history = rounds()
        fake = FakeGitHub(history, pr_history.render_history(history, []))
        self._install(fake)
        with mock.patch("ffbuild.autoheal.delivery.write_pr_body",
                        side_effect=RuntimeError("Simulated PR body HTTP failure")):
            with self.assertRaisesRegex(RuntimeError, "Simulated PR body HTTP"):
                delivery.sync_status(ci_report(C2, "success"))
        self.assertEqual(3, len(fake.comments))
        delivery.sync_status(ci_report(C2, "success"))
        self.assertEqual(3, len(fake.comments))
        self.assertIn("| 1 |", fake.pr["body"])
        self.assertIn("[Passed (Run", fake.pr["body"])
        self.assertEqual(1, fake.write_calls)

    def test_missing_pr_body_recovers_both_rounds_and_preserves_human_notes(self):
        history = rounds()
        fake = FakeGitHub(history, "Maintainer summary without bot markers")
        self._install(fake)
        delivery.sync_status(ci_report(C2, "success"))
        body = fake.pr["body"]
        self.assertIn("Maintainer summary without bot markers", body)
        self.assertIn("| 1 |", body)
        self.assertIn("[Passed (Run", body)
        self.assertEqual(3, len(fake.comments))
        delivery.sync_status(ci_report(C2, "success"))
        self.assertEqual(3, len(fake.comments))

    def test_resume_submitted_pr_after_comment_failure(self):
        history = rounds()[:1]
        fake = FakeGitHub(history, pr_history.render_history(history, []))
        self._install(fake)
        report = {"source": {"run_id": 101, "run_attempt": 1}}
        with mock.patch("ffbuild.autoheal.delivery._ensure_auto_merge") as enable:
            self.assertTrue(delivery._resume_submitted_pr(
                fake.pr, INCIDENT, report, "d" * 40))
            self.assertTrue(delivery._resume_submitted_pr(
                fake.pr, INCIDENT, report, "d" * 40))
            self.assertEqual(2, enable.call_count)
        self.assertEqual(1, len(fake.comments))
        self.assertEqual(0, fake.write_calls)  # existing summary was already current

    def test_human_edit_during_ci_sync_is_preserved(self):
        history = rounds()
        fake = FakeGitHub(history, pr_history.render_history(history, []))
        self._install(fake)
        original = fake.collection
        def edit_mid_sync(endpoint, key, **kwargs):
            if endpoint.endswith("/pulls/42/files"):
                fake.pr["body"] = "New manual note\n\n" + fake.pr["body"]
            return original(endpoint, key, **kwargs)
        with mock.patch("ffbuild.autoheal.pr_history.github.collection",
                        side_effect=edit_mid_sync):
            delivery.sync_status(ci_report(C2, "failure"))
        self.assertIn("New manual note", fake.pr["body"])

    def test_large_cumulative_diff_is_summarized_with_full_history_intact(self):
        history = rounds()
        paths = [f"patches/8.x/{i:03d}-" + "q" * 230 + ".patch"
                 for i in range(301)]
        body = pr_history.render_history(history, events(), cumulative_paths=paths)
        self.assertLess(len(body), 60_000)
        self.assertIn("261 additional files", body)
        self.assertIn("| 1 |", body)
        self.assertIn("| 2 |", body)

    def test_lost_comment_is_repaired_from_bot_commit(self):
        history = rounds()
        fake = FakeGitHub(history, pr_history.render_history(history, []))
        self._install(fake)
        delivery.sync_status(ci_report(C2, "failure"))
        keys = [pr_history.parse_event(comment, INCIDENT, history).key
                for comment in fake.comments]
        self.assertEqual(3, len(keys))
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
