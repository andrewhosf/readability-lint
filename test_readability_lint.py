"""Control suite for readability_lint — stdlib unittest, no deps.

These controls are the reason the shipped thresholds are trusted: the first
version of the module failed two of them (a bound-method key bug that would
have made every call take the fail-open path, and a <2-sentence skip rule
that excluded the single-run-on case the lint exists to catch).
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LINT = os.path.join(HERE, "readability_lint.py")
sys.path.insert(0, HERE)
import readability_lint as rl  # noqa: E402

CLEAN = (
    "The lane restart finished. VRAM was verified at zero before relaunch. "
    "The model is healthy and answering requests on the primary port. "
    "Logs show no errors in the first ten minutes after boot. "
) * 3

RUNON = (
    "Go and I'll label the rows from the ledger, download the checkpoint to "
    "the box, and return the measured table, replacing the illustrative "
    "numbers with figures drawn from your own traffic, before any unit or "
    "config line gets written, which is the point I was making earlier, and "
    "the reason the plan was staged that way, because measurement has to "
    "precede configuration in every lane we run, which is the doctrine we "
    "adopted after the last incident taught us what unmeasured flags "
    "actually cost the fleet over a quarter of quiet afternoons."
)


class TestLint(unittest.TestCase):
    def test_fragment_skips(self):
        v = rl.lint("DONE\n")
        self.assertEqual(v["verdict"], "skip")

    def test_table_bullets_only_skips(self):
        text = "\n".join(
            ["| a | b | c |"] * 20 + ["- bullet item one", "- bullet two"] * 10)
        self.assertEqual(rl.lint(text)["verdict"], "skip")

    def test_clean_prose_passes(self):
        v = rl.lint(CLEAN)
        self.assertEqual(v["verdict"], "pass")
        self.assertLess(v["metrics"]["fk_grade"], 8)

    def test_single_runon_fails_both_surfaces(self):
        # the target pathology: ONE giant sentence must never be skipped
        for surf in ("user", "tech"):
            v = rl.lint(RUNON, surface=surf)
            self.assertEqual(v["verdict"], "fail", surf)
            self.assertTrue(any("sentence nesting" in r for r in v["reasons"]))

    def test_semicolon_counts_as_sentence_break(self):
        # 40-word clause chains joined by ';' should NOT be one sentence
        seg = ("The report showed that the system was restarted under load, "
               "which the team had expected after the maintenance window, "
               "and the logs confirmed a clean recovery with no follow-up ")
        text = "; ".join([seg.strip()] * 8) + "."
        v = rl.lint(text)
        self.assertLessEqual(v["metrics"]["max_sent_words"], 45)

    def test_newline_counts_as_sentence_break(self):
        # markdown bullet chains must not merge into one mega-sentence
        line = ("the lane completed its warmup and the companion checks ran "
                "against fresh state, which proved the ordering was correct ")
        text = "\n".join(["- " + line.strip() + "." for _ in range(8)])
        v = rl.lint(text)
        self.assertLessEqual(v["metrics"]["max_sent_words"], 45)

    def test_length_budget_fires(self):
        v = rl.lint(CLEAN * 4)  # >350 words of grade-3 prose
        self.assertEqual(v["verdict"], "fail")
        self.assertTrue(any(r.startswith("length") for r in v["reasons"]))

    def test_metrics_shape_is_contract_stable(self):
        m = rl.lint(RUNON)["metrics"]
        for key in ("fk_grade", "max_sent_words", "max_sent_clauses",
                    "words", "sentences", "mean_sent_words", "worst_sentence"):
            self.assertIn(key, m)


class TestCli(unittest.TestCase):
    def run_cli(self, args, stdin=None):
        return subprocess.run(
            [sys.executable, LINT] + args, input=stdin,
            capture_output=True, text=True)

    def test_exit_codes(self):
        self.assertEqual(self.run_cli([], "DONE\n").returncode, 0)
        self.assertEqual(
            self.run_cli([], CLEAN).returncode, 0)
        self.assertEqual(
            self.run_cli(["--json"], RUNON).returncode, 1)

    def test_shadow_always_zero(self):
        self.assertEqual(
            self.run_cli(["--shadow"], RUNON).returncode, 0)

    def test_missing_file_fails_open(self):
        r = self.run_cli(["/nonexistent/path.md"])
        self.assertEqual(r.returncode, 0)          # fail-open by contract
        self.assertIn('"error"', r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
