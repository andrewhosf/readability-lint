# readability-lint

A deterministic, dependency-free readability/conciseness linter for
LLM-agent output. No model, no network, no training data — pure functions
over text, with a verdict shape designed to plug into a pre-delivery
verification hook.

```
$ python3 readability_lint.py --json long-reply.md
{
  "verdict": "fail",
  "reasons": [
    "sentence nesting: worst 92w/15 clauses (cap 45w)",
    "FK grade 38.8 > cap 10"
  ],
  "surface": "user",
  "metrics": { "fk_grade": 38.8, "max_sent_words": 92, "max_sent_clauses": 15,
               "words": 92, "sentences": 1, "mean_sent_words": 92.0,
               "worst_sentence": "Go and I'll label the rows from the ledger, download..." }
}
$ echo $?
1
```

## Why a lint and not a model

Readability and conciseness are measurements, not judgments. Flesch-Kincaid
grade, words-per-sentence, clause count, and length budget are arithmetic —
so unlike a model-based judge (which needs a calibration gauntlet: positive
controls, AUC, ECE), this ships with a control suite and a corpus-calibrated
threshold table. It cannot be "out of domain," because there is nothing
learned in it.

## Design rules (each learned the hard way)

1. **Primary metric is clause nesting, not vocabulary.** The real failure
   mode of agent prose is one 60+ word chained sentence, not hard words.
   FK grade is secondary; a long technical noun phrase should not fail.
2. **Fragment guard.** Prose under 30 words, or text that is mostly code
   fences / tables / URLs after stripping, is `skip`, never scored. A bare
   `DONE` status message naively FK-scores at grade ~100; a lint that
   flags status pings is a lint that gets disabled.
3. **Fail-open is structural.** Any internal error prints
   `{"verdict": "error", ...}` and exits 0. A verifier that can block
   delivery is a new single point of failure.
4. **Calibrate on real traffic, not vibes.** Thresholds here come from a
   sweep grid over 400 real agent replies (see below). A first config
   derived from the "10th grade" rule of thumb made 270 of those 400
   replies (68%) FAIL — it was measuring style, not readability. A gate
   that cries wolf is a dead gate.

## Thresholds

| Surface | FK grade cap | Max words/sentence | Word budget |
|---|---|---|---|
| `user` (summaries, notifications) | 10 | 45 | 350 |
| `tech` (expert prose) | 14 | 45 | 600 |

Clause count is reported in metrics and only fires on its own at ≥ 12
clauses in one sentence (density guard for run-ons with few commas).
Sentence boundaries: `.!?` + `;` + newline.

Calibration on 400 real assistant replies (dense technical agent traffic,
code/tables/URLs stripped):

| Config | user fail % | tech fail % |
|---|---|---|
| 28-word cap (naive) | 68 | 45 |
| **45-word cap + `;`-split (shipped)** | **13** | **7** |

The 13%/7% remainder were spot-checked: they are genuinely long chained
sentences, not artifacts.

## API

```python
from readability_lint import lint

v = lint(text, surface="user")
# v["verdict"]  in {"pass", "fail", "skip", "error"}
# v["reasons"]  list of human-readable failed invariants
# v["metrics"]  fk_grade, max_sent_words, max_sent_clauses, words,
#               sentences, mean_sent_words, worst_sentence
```

The dict is intentionally shaped like a verifier verdict
(`{verdict, reasons, metrics}`) so an annotate/instruct-mode hook can
consume it without a rewrite.

## CLI

```
python3 readability_lint.py [--surface user|tech] [--json] [--shadow] [FILE]
```

Exit codes: `0` pass/skip/error/shadow · `1` fail (enforce mode).
Shadow mode is the recommended first integration: log verdicts, change
nothing.

## Tests

```
python3 -m unittest test_readability_lint -v
```

The suite is the reason the shipped thresholds are trusted — earlier
revisions failed two of these controls in ways static review missed
(a bound-method key bug that routed every call through the fail-open path,
and a `skip` rule that excluded the single-run-on case the lint exists to
catch). Keep both classes green when tuning.

## Known limitations

- FK is calibrated for English; mixed-language text scores unreliably.
- `_clauses()` is a heuristic (commas + conjunctions + dashes), not a
  parser — reported, and hard-gated only at the extreme.
- No semantic checks by design: whether the text is *true* needs a
  different verifier (an entailment judge, ideally option logprobs off a
  long-context model — a small encoder classifier is measurably the wrong
  tool for that, which is the origin story of this one).

## License

MIT
