"""ml/rules.py  --  match a narrative to the IOGP Life-Saving Rules"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = ROOT / "data" / "reference" / "iogp_life_saving_rules.json"

STOP = {
    "i", "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "is", "are",
    "was", "were", "be", "been", "it", "its", "my", "me", "we", "for", "from",
    "with", "that", "this", "have", "has", "had", "do", "does", "did", "not",
    "before", "after", "while", "when", "which", "any", "all", "no", "he", "she",
    "his", "her", "they", "them", "there", "then", "than", "as", "by", "if",
    "work", "working", "worker", "use", "used", "using", "make", "made", "get",
    "out", "off", "up", "down", "over", "under", "into", "onto", "front", "back",
    "stand", "standing", "still", "high", "low", "one", "two", "who", "during",
    "been", "being", "other", "others", "own", "only", "also", "very", "just",
    "confirm", "confirmed", "obtain", "understand", "identify", "identified",
    "check", "checked", "take", "taken", "report", "reported", "reports",
}


def stem(word: str) -> str:
    """Crude suffix stripping so 'lifting'/'lift' and 'isolated'/'isolation' meet."""
    w = word.lower()
    for suf in ("ations", "ation", "ings", "ing", "ies", "ied", "ers", "er",
                "eds", "ed", "es", "s"):
        if len(w) - len(suf) >= 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def same_word(a: str, b: str, min_prefix: int = 4) -> bool:
    """Whether two stems refer to the same concept."""
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= min_prefix and long_.startswith(short)


def tokens(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z]+", text.lower())
            if w not in STOP and len(w) > 2}


@dataclass
class RuleMatch:
    rule_id: str
    rule_name: str
    action: str
    confidence: float
    evidence: list[str]
    suggested_checks: list[str]
    source: str

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "action": self.action,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
            "suggested_checks": self.suggested_checks,
            "source": self.source,
        }


@dataclass
class Analysis:
    matched_rules: list[RuleMatch] = field(default_factory=list)
    unmatched: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "matched_rules": [m.to_dict() for m in self.matched_rules],
            "unmatched": self.unmatched,
            "note": self.note,
        }


class RuleMatcher:
    """Matches narratives against the nine IOGP Life-Saving Rules."""

    W_PHRASE = 3.0
    W_SIGNAL = 2.0
    W_VOCAB = 0.5
    SATURATE = 6.0

    def __init__(self, path: str | Path = RULES_FILE):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.source = data["source"]
        self.rules = data["rules"]
        self._prepared = []
        for r in self.rules:
            phrases = [s.lower() for s in r["signals"] if " " in s]
            singles = {stem(s) for s in r["signals"] if " " not in s}
            vocab = set()
            for c in r["commitments"]:
                vocab |= tokens(c)
            vocab |= tokens(r["action"]) | tokens(r["name"])
            vocab -= singles
            self._prepared.append((r, phrases, singles, vocab))

    def _score(self, text: str, toks: set[str], phrases, singles, vocab):
        """Returns (score, evidence, core) where `core` counts signal hits only."""
        hits, score, core = [], 0.0, 0
        low = text.lower()
        for p in phrases:
            if p in low:
                score += self.W_PHRASE
                core += 1
                hits.append(p)
        for s in singles:
            if any(same_word(t, s) for t in toks):
                score += self.W_SIGNAL
                core += 1
                hits.append(s)
        overlap = {t for t in toks if any(same_word(t, v) for v in vocab)}
        score += self.W_VOCAB * min(len(overlap), 4)
        hits.extend(sorted(overlap)[:4])
        return score, hits, core

    def match(self, narrative: str, min_confidence: float = 0.18,
              top_k: int = 3) -> Analysis:
        """Rules this narrative plausibly touches, most likely first."""
        toks = tokens(narrative)
        if not toks:
            return Analysis(unmatched=True, note="Narrative too short to classify.")

        scored = []
        for r, phrases, singles, vocab in self._prepared:
            s, hits, core = self._score(narrative, toks, phrases, singles, vocab)
            if core:
                scored.append((s, r, hits))
        if not scored:
            return Analysis(
                unmatched=True,
                note="No Life-Saving Rule matched. This does not mean the report is "
                     "low risk -- read the SIF score, which is independent of this.",
            )

        out = []
        for s, r, hits in sorted(scored, key=lambda x: -x[0])[:top_k]:
            conf = min(1.0, s / self.SATURATE)
            if conf < min_confidence:
                continue
            out.append(RuleMatch(
                rule_id=r["id"], rule_name=r["name"], action=r["action"],
                confidence=conf,
                evidence=sorted(set(hits))[:8],
                suggested_checks=r["commitments"],
                source=f"{self.source['title']}, {self.source['report']}",
            ))
        if not out:
            return Analysis(unmatched=True, note="No rule matched strongly enough.")
        return Analysis(
            matched_rules=out,
            note="Draft for HSE review. Suggested checks are the IOGP commitments "
                 "verbatim; they are not generated and not tailored to this "
                 "incident. Confidence is wording similarity, not risk.",
        )


_MATCHER: RuleMatcher | None = None


def get_matcher() -> RuleMatcher:
    """Process-wide singleton; the rules file is small but constant."""
    global _MATCHER
    if _MATCHER is None:
        _MATCHER = RuleMatcher()
    return _MATCHER


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Match a narrative to IOGP Life-Saving Rules")
    ap.add_argument("text", nargs="*", help="the narrative")
    args = ap.parse_args()
    text = " ".join(args.text) or input("narrative> ")

    m = get_matcher()
    a = m.match(text)
    print(f"\n  {text}\n")
    if a.unmatched:
        print(f"  {a.note}")
        return
    for r in a.matched_rules:
        print(f"  {r.confidence:.2f}  {r.rule_name} -- {r.action}")
        print(f"        matched on: {', '.join(r.evidence)}")
        for c in r.suggested_checks:
            print(f"        [ ] {c}")
        print(f"        source: {r.source}")
        print()
    print(f"  {a.note}")


if __name__ == "__main__":
    main()
