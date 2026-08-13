#!/usr/bin/env python3
"""Mechanically detect repetition, filler, and AI-writing patterns in a LaTeX CV.

Used by the cv-sanity-check skill. Detection is deterministic here so nothing is
missed by judgment alone; deciding how to *fix* each finding stays with the skill.

Usage:
    ./check-cv-text.py [path/to/cv.tex]     # defaults to ./cv.tex
    ./check-cv-text.py --json cv.tex        # machine-readable output

Exit codes:  0 = no findings, 1 = findings reported, 2 = usage/IO error.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter, defaultdict

# ---------------------------------------------------------------- word lists

# Words that carry no signal for repetition analysis.
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "that", "this",
    "these", "those", "of", "to", "in", "on", "at", "by", "for", "with", "from",
    "as", "into", "over", "under", "via", "per", "is", "are", "was", "were", "be",
    "been", "being", "it", "its", "their", "his", "her", "them", "they", "we",
    "our", "us", "i", "my", "me", "you", "your", "not", "no", "all", "each",
    "both", "more", "most", "other", "some", "such", "own", "same", "so", "up",
    "out", "about", "across", "after", "before", "between", "during", "while",
    "where", "when", "which", "who", "whom", "how", "what", "can", "will",
    "would", "should", "could", "may", "might", "must", "do", "does", "did",
    "have", "has", "had", "also", "new", "using", "used", "use", "one", "two",
}

# Phrases that add length without adding information.
FILLER_PHRASES = [
    "responsible for", "worked on", "helped with", "assisted with", "tasked with",
    "duties included", "involved in", "participated in", "in order to",
    "with the goal of", "for the purpose of", "a variety of", "a number of",
    "various", "several", "numerous", "successfully", "effectively",
    "efficiently", "significantly", "substantially", "greatly", "highly",
    "very", "extremely", "utilized", "utilizing", "aimed to", "sought to",
    "was able to", "had the opportunity to", "gained experience", "exposure to",
    "familiar with", "knowledge of", "hands-on experience",
]

# Words that read as AI-generated or as resume padding.
BUZZWORDS = [
    "spearheaded", "spearhead", "leveraged", "leverage", "leveraging",
    "orchestrated", "orchestrating", "synergy", "synergies", "cutting-edge",
    "state-of-the-art", "best-in-class", "world-class", "transformative",
    "innovative", "groundbreaking", "revolutionary", "seamless", "seamlessly",
    "robust", "comprehensive", "holistic", "dynamic", "passionate",
    "detail-oriented", "team player", "results-driven", "self-starter",
    "go-getter", "thought leadership", "paradigm", "game-changing",
    "mission-critical", "next-generation", "unparalleled", "unlock", "empower",
    "elevate", "delve", "myriad", "plethora", "tapestry", "realm", "landscape",
    "underscore", "pivotal", "crucial", "vital", "meticulous", "meticulously",
]

# Thresholds
OPENER_REPEAT_LIMIT = 1      # same opening word more than this = flagged
CONTENT_WORD_LIMIT = 3       # content word appearing more than this = flagged
BUZZWORD_LIMIT = 0           # buzzwords are flagged on any occurrence
EM_DASH_LIMIT = 3            # em dashes across the document
UNIFORMITY_CV_THRESHOLD = 0.15   # coefficient of variation below this = templated


# ---------------------------------------------------------------- extraction

def strip_latex(text: str) -> str:
    """Reduce a LaTeX fragment to readable prose."""
    # \href{url}{shown} -> shown   (drop the URL, keep the label)
    text = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", text)
    # \textbf{x} / \emph{x} / \textit{x} / \underline{x} -> x
    text = re.sub(r"\\(?:textbf|emph|textit|underline|small|large)\{([^{}]*)\}", r"\1", text)
    # math-mode helpers commonly used for tilde / dollar
    text = text.replace(r"$\sim$", "~").replace(r"\$", "$")
    # escaped specials
    text = re.sub(r"\\([%&#_])", r"\1", text)
    # any remaining control sequences
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    # leftover braces and math delimiters
    text = text.replace("{", " ").replace("}", " ").replace("$", " ")
    return re.sub(r"\s+", " ", text).strip()


def extract_bullets(source: str) -> list[tuple[int, str]]:
    """Return (line_number, prose) for each CV bullet.

    Handles both the plain `\\item ...` form and the `\\resumeItem{...}` wrapper
    used by the common sb2nov-derived templates.
    """
    bullets: list[tuple[int, str]] = []
    for lineno, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("%"):
            continue

        m = re.match(r"\\resumeItem\{(.*)\}\s*$", stripped)
        if m:
            body = m.group(1)
        elif stripped.startswith(r"\item"):
            body = stripped[len(r"\item"):]
        else:
            continue

        prose = strip_latex(body)
        # Skip section scaffolding that isn't a real accomplishment bullet.
        if len(prose) < 25:
            continue
        bullets.append((lineno, prose))
    return bullets


def words_of(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z'\-]+", text.lower())


def plural(n: int, noun: str) -> str:
    return noun if n == 1 else noun + "s"


# ---------------------------------------------------------------- detectors

def check_openers(bullets):
    """Bullets that begin with the same word."""
    groups = defaultdict(list)
    for lineno, prose in bullets:
        w = words_of(prose)
        if w:
            groups[w[0]].append(lineno)
    out = []
    for word, lines in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(lines) > OPENER_REPEAT_LIMIT:
            out.append({
                "type": "repeated-opener",
                "detail": f"{len(lines)} bullets open with '{word}'",
                "lines": lines,
            })
    return out


def check_repeated_words(bullets):
    """Content words used more often than a human resume would."""
    counts = Counter()
    where = defaultdict(set)
    for lineno, prose in bullets:
        for w in set(words_of(prose)):        # count each bullet once per word
            if w in STOPWORDS or len(w) < 4:
                continue
            counts[w] += 1
            where[w].add(lineno)
    out = []
    for word, n in counts.most_common():
        if n > CONTENT_WORD_LIMIT:
            out.append({
                "type": "repeated-word",
                "detail": f"'{word}' appears in {n} separate bullets",
                "lines": sorted(where[word]),
            })
    return out


def check_phrases(bullets, phrases, kind, limit):
    """Filler phrases / buzzwords, matched on word boundaries."""
    hits = defaultdict(list)
    for lineno, prose in bullets:
        low = prose.lower()
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", low):
                hits[phrase].append(lineno)
    out = []
    for phrase, lines in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        if len(lines) > limit or kind == "filler":
            out.append({
                "type": kind,
                "detail": f"'{phrase}' \u00d7{len(lines)}",
                "lines": lines,
            })
    return out


def check_em_dashes(bullets):
    total = 0
    lines = []
    for lineno, prose in bullets:
        n = prose.count("\u2014") + prose.count("---")
        if n:
            total += n
            lines.append(lineno)
    if total > EM_DASH_LIMIT:
        return [{
            "type": "em-dash-overuse",
            "detail": f"{total} em {plural(total, 'dash')} across {len(lines)} {plural(len(lines), 'bullet')}",
            "lines": lines,
        }]
    return []


def check_uniformity(bullets):
    """Bullets all near-identical in length read as templated."""
    if len(bullets) < 4:
        return []
    lengths = [len(p) for _, p in bullets]
    mean = statistics.mean(lengths)
    if mean == 0:
        return []
    cv = statistics.pstdev(lengths) / mean
    if cv < UNIFORMITY_CV_THRESHOLD:
        return [{
            "type": "uniform-length",
            "detail": (f"bullet lengths unusually uniform "
                       f"(mean {mean:.0f} chars, variation {cv:.0%})"),
            "lines": [ln for ln, _ in bullets],
        }]
    return []


# Quantities written as words still count as quantification.
WORD_NUMBERS = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"dozen|dozens|hundred|hundreds|thousand|thousands|million|millions|"
    r"billion|billions|half|double|doubled|triple|tripled|quadrupled)\b",
    re.IGNORECASE,
)


def check_unquantified(bullets):
    """Impact bullets with no quantity at all, in digits or words."""
    lines = [
        ln for ln, p in bullets
        if not re.search(r"\d", p) and not WORD_NUMBERS.search(p)
    ]
    if lines:
        return [{
            "type": "unquantified",
            "detail": (f"{len(lines)} {plural(len(lines), 'bullet')} "
                       f"carry no quantity of any kind"),
            "lines": lines,
        }]
    return []


# ---------------------------------------------------------------- reporting

SEVERITY = {
    "buzzword": 1, "filler": 2, "repeated-opener": 3, "repeated-word": 4,
    "em-dash-overuse": 5, "uniform-length": 6, "unquantified": 7,
}

LABELS = {
    "buzzword": "Buzzwords",
    "filler": "Filler phrases",
    "repeated-opener": "Repeated bullet openers",
    "repeated-word": "Overused words",
    "em-dash-overuse": "Em-dash overuse",
    "uniform-length": "Uniform bullet length",
    "unquantified": "Unquantified bullets",
}


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    as_json = "--json" in argv
    path = args[0] if args else "cv.tex"

    try:
        source = open(path, encoding="utf-8").read()
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    bullets = extract_bullets(source)
    if not bullets:
        print(f"error: no bullets found in {path} — is it a CV?", file=sys.stderr)
        return 2

    findings = (
        check_phrases(bullets, BUZZWORDS, "buzzword", BUZZWORD_LIMIT)
        + check_phrases(bullets, FILLER_PHRASES, "filler", 0)
        + check_openers(bullets)
        + check_repeated_words(bullets)
        + check_em_dashes(bullets)
        + check_uniformity(bullets)
        + check_unquantified(bullets)
    )
    findings.sort(key=lambda f: SEVERITY.get(f["type"], 99))

    if as_json:
        print(json.dumps({
            "file": path,
            "bullets": len(bullets),
            "findings": findings,
        }, indent=2))
        return 1 if findings else 0

    print(f"{path}: {len(bullets)} bullets analyzed")
    if not findings:
        print("\nNo mechanical findings. Still read it for tone and cadence.")
        return 0

    current = None
    for f in findings:
        if f["type"] != current:
            current = f["type"]
            print(f"\n{LABELS.get(current, current)}")
        lines = ", ".join(f"L{n}" for n in f["lines"][:12])
        more = "" if len(f["lines"]) <= 12 else f" (+{len(f['lines']) - 12} more)"
        print(f"  - {f['detail']}  [{lines}{more}]")

    print(f"\n{len(findings)} finding(s). These are signals, not verdicts — a repeated "
          "domain term\nmay be unavoidable. Judge each before rewriting.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
