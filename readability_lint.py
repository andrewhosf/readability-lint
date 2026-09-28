#!/usr/bin/env python3
"""Readability/conciseness lint — deterministic, stdlib-only, no model.

Verdict shape mirrors a verifier contract: {verdict, metrics, reasons} so an
annotate/instruct hook can consume it later without a rewrite.

Design rules (from measured findings, sep-28):
  * Primary metric = clause nesting (max words/sentence, clause count),
    NOT vocabulary grade. FK grade is secondary.
  * Fragment guard: prose under MIN_WORDS or mostly non-prose (tables, code,
    URLs, lists) is SKIPPED, never scored — a bare "DONE" must not flag.
  * Per-surface thresholds: surface="user" grade<=10 / 28-word sentence cap;
    surface="tech"  grade<=14 / 40-word cap.
  * Fail-open: any internal error prints verdict=error and exits 0 (lint
    absence must never block delivery).

Usage:
  readability_lint.py [--surface user|tech] [--json] [--shadow] < file.md
  exit 0 = pass or skipped or shadow-mode;  exit 1 = fail (enforce mode)
"""
import argparse
import json
import re
import sys

MIN_WORDS = 30          # fragment guard: below this, skip (status pings)
PROSE_FLOOR = 0.5       # <50% of words surviving strip => not prose, skip

FENCE = re.compile(r"```.*?```", re.S)
INLN = re.compile(r"`[^`]*`")
URL = re.compile(r"https?://\S+")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|;\s+|\n+")   # ';' = sentence break (calibrated)


def _strip_nonprose(t: str) -> tuple[str, float]:
    n_all = len(re.findall(r"[A-Za-z']+", t)) or 1
    t = FENCE.sub(" ", t)
    t = "\n".join(l for l in t.splitlines() if "|" not in l)   # table rows
    t = re.sub(r"^#+\s+.*$", " ", t, flags=re.M)               # headings
    t = re.sub(r"^\s*[-*]\s+", "", t, flags=re.M)              # bullet markers
    t = INLN.sub(" ", t)
    t = URL.sub(" ", t)
    t = BOLD.sub(r"\1", t)
    n_kept = len(re.findall(r"[A-Za-z']+", t))
    return t, n_kept / n_all


def _syl(w: str) -> int:
    w = re.sub(r"[^a-z]", "", w.lower())
    if not w:
        return 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and n > 1 and not w.endswith(("le", "ee", "ye")):
        n -= 1
    return max(1, n)


def _clauses(s: str) -> int:
    """Rough clause count: commas + coordinating conjunctions + dashes + 1."""
    return 1 + s.count(",") + len(re.findall(r"\b(?:and|but|which|while|since|because)\b", s, re.I)) + s.count("—") + s.count(" -- ")


def lint(text: str, surface: str = "user") -> dict:
    if surface == "tech":
        grade_cap, sent_cap, len_cap = 14.0, 45, 600
    else:
        grade_cap, sent_cap, len_cap = 10.0, 45, 350
    # caps calibrated 2026-09-28 on 400 real assistant replies (sweep grid):
    # 45-word cap + ';' split -> 13% of replies fail (user surface), 7% (tech).
    # The earlier 28-word cap made 68% of replies FAIL (270/400) — it was
    # measuring style, not readability. A gate that cries wolf is a dead gate.

    t, kept = _strip_nonprose(text)
    words = re.findall(r"[A-Za-z']+", t)
    if len(words) < MIN_WORDS or kept < PROSE_FLOOR:
        return {"verdict": "skip", "reason": "non-prose or fragment",
                "metrics": {"words": len(words), "prose_frac": round(kept, 2)}}

    sents = [s for s in SENT_SPLIT.split(t) if len(s.split()) >= 4]
    if not sents:
        return {"verdict": "skip", "reason": "no sentences after strip",
                "metrics": {"words": len(words)}}
    # NOTE: exactly-1-sentence is NOT skipped — one giant run-on is the target
    # pathology (caught via max_sent_words below), not a fragment.

    W, S = len(words), len(sents)
    SY = sum(_syl(w) for w in words)
    fk = 0.39 * (W / S) + 11.8 * (SY / W) - 15.59
    worst = max(sents, key=lambda s: len(s.split()))
    worst_w, worst_c = len(worst.split()), _clauses(worst)

    reasons = []
    if worst_w > sent_cap:
        reasons.append(f"sentence nesting: worst {worst_w}w/{worst_c} clauses (cap {sent_cap}w)")
    elif worst_c >= 12:
        reasons.append(f"clause density: worst sentence {worst_c} clauses")
    if fk > grade_cap:
        reasons.append(f"FK grade {fk:.1f} > cap {grade_cap:.0f}")
    if W > len_cap:
        reasons.append(f"length {W}w > budget {len_cap}w")
    return {"verdict": "fail" if reasons else "pass", "reasons": reasons,
            "surface": surface,
            "metrics": {"fk_grade": round(fk, 1), "max_sent_words": worst_w,
                        "max_sent_clauses": worst_c, "words": W,
                        "sentences": S, "mean_sent_words": round(W / S, 1),
                        "worst_sentence": worst[:120]}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surface", choices=["user", "tech"], default="user")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--shadow", action="store_true",
                    help="log verdict but always exit 0")
    ap.add_argument("file", nargs="?", help="default: stdin")
    a = ap.parse_args()
    try:
        text = open(a.file).read() if a.file else sys.stdin.read()
        r = lint(text, a.surface)
    except Exception as e:                       # fail-open by contract
        r = {"verdict": "error", "reason": str(e)}
    print(json.dumps(r, indent=2 if a.json else None))
    if a.shadow or r["verdict"] in ("pass", "skip", "error"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
