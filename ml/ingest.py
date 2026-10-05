#!/usr/bin/env python3
"""ml/ingest.py  --  make a field report readable by a model trained on English"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
LEXICON_FILE = ROOT / "data" / "reference" / "domain_lexicon.json"


DEVANAGARI_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "ळ": "l",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f",
}
DEVANAGARI_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
}
DEVANAGARI_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ii", "ु": "u", "ू": "uu",
    "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
}
DEVANAGARI_SIGNS = {"ं": "n", "ँ": "n", "ः": "h", "़": "", "।": ".", "॥": "."}

BENGALI_CONSONANTS = {
    "ক": "k", "খ": "kh", "গ": "g", "ঘ": "gh", "ঙ": "ng",
    "চ": "ch", "ছ": "chh", "জ": "j", "ঝ": "jh", "ঞ": "ny",
    "ট": "t", "ঠ": "th", "ড": "d", "ঢ": "dh", "ণ": "n",
    "ত": "t", "থ": "th", "দ": "d", "ধ": "dh", "ন": "n",
    "প": "p", "ফ": "ph", "ব": "b", "ভ": "bh", "ম": "m",
    "য": "j", "র": "r", "ল": "l", "শ": "sh", "ষ": "sh", "স": "s", "হ": "h",
    "ড়": "r", "ঢ়": "rh", "য়": "y", "ৎ": "t",
    "ৰ": "r", "ৱ": "w",
}
BENGALI_VOWELS = {
    "অ": "a", "আ": "aa", "ই": "i", "ঈ": "ii", "উ": "u", "ঊ": "uu",
    "ঋ": "ri", "এ": "e", "ঐ": "oi", "ও": "o", "ঔ": "ou",
}
BENGALI_MATRAS = {
    "া": "aa", "ি": "i", "ী": "ii", "ু": "u", "ূ": "uu",
    "ৃ": "ri", "ে": "e", "ৈ": "oi", "ো": "o", "ৌ": "ou",
}
BENGALI_SIGNS = {"ং": "ng", "ঁ": "n", "ঃ": "h", "়": "", "।": "."}

DEVANAGARI_VIRAMA = "्"
BENGALI_VIRAMA = "্"

SCRIPTS = {
    "devanagari": (DEVANAGARI_CONSONANTS, DEVANAGARI_VOWELS, DEVANAGARI_MATRAS,
                   DEVANAGARI_SIGNS, DEVANAGARI_VIRAMA, "०", "९"),
    "bengali": (BENGALI_CONSONANTS, BENGALI_VOWELS, BENGALI_MATRAS,
                BENGALI_SIGNS, BENGALI_VIRAMA, "০", "৯"),
}


def detect_scripts(text: str) -> list[str]:
    """Which writing systems appear. A field report often mixes all three."""
    found = set()
    for ch in text:
        code = ord(ch)
        if 0x0900 <= code <= 0x097F:
            found.add("devanagari")
        elif 0x0980 <= code <= 0x09FF:
            found.add("bengali")
        elif ch.isalpha() and code < 0x250:
            found.add("latin")
    return sorted(found)


def delete_final_schwa(word: str) -> str:
    """Drop the word-final inherent vowel, as every one of these languages does."""
    if len(word) >= 3 and word.endswith("a") and not word.endswith("aa"):
        return word[:-1]
    return word


def _transliterate_script(text: str, script: str) -> str:
    cons, vowels, matras, signs, virama, digit0, _ = SCRIPTS[script]
    out: list[str] = []
    word: list[str] = []
    i = 0
    n = len(text)

    def flush() -> None:
        if word:
            out.append(delete_final_schwa("".join(word)))
            word.clear()

    while i < n:
        ch = text[i]
        pair = text[i:i + 2]
        if pair in cons:
            ch, step = pair, 2
        elif ch in cons:
            step = 1
        else:
            step = 0

        if step:
            word.append(cons[ch])
            nxt = text[i + step] if i + step < n else ""
            if nxt == virama:
                i += step + 1
                continue
            if nxt in matras:
                word.append(matras[nxt])
                i += step + 1
                continue
            word.append("a")
            i += step
            continue

        if ch in vowels:
            word.append(vowels[ch])
        elif ch in matras:
            word.append(matras[ch])
        elif ch in signs:
            if signs[ch] in (".", ""):
                flush()
                out.append(signs[ch])
            else:
                word.append(signs[ch])
        elif digit0 <= ch <= chr(ord(digit0) + 9):
            flush()
            out.append(str(ord(ch) - ord(digit0)))
        elif ch == virama:
            pass
        else:
            flush()
            out.append(ch)
        i += 1

    flush()
    return "".join(out)


def transliterate(text: str) -> str:
    """Indic scripts to Latin, leaving everything else untouched."""
    for script in ("devanagari", "bengali"):
        if any(s == script for s in detect_scripts(text)):
            text = _transliterate_script(text, script)
    return text


def edit_distance_at_most_1(a: str, b: str) -> bool:
    """Damerau-Levenshtein distance <= 1, short-circuited on length."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2 and diffs[1] == diffs[0] + 1:
            i, j = diffs
            return a[i] == b[j] and a[j] == b[i]
        return False
    short, long_ = (a, b) if la < lb else (b, a)
    for i in range(len(long_)):
        if long_[:i] + long_[i + 1:] == short:
            return True
    return False


@dataclass
class Change:
    step: str
    before: str
    after: str

    def to_dict(self) -> dict:
        return {"step": self.step, "before": self.before, "after": self.after}


@dataclass
class Normalised:
    """What the model will read, next to what was written, and every step between."""

    text: str
    original: str
    scripts: list[str] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)

    @property
    def modified(self) -> bool:
        return self.text.strip() != self.original.strip()

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "original": self.original,
            "scripts": self.scripts,
            "modified": self.modified,
            "changes": [c.to_dict() for c in self.changes],
        }

    def describe(self) -> str:
        lines = [f"  in  : {self.original}", f"  out : {self.text}"]
        if self.scripts:
            lines.append(f"  scripts: {', '.join(self.scripts)}")
        if self.changes:
            lines.append("  changes:")
            for c in self.changes:
                lines.append(f"    [{c.step:<13}] {c.before!r} -> {c.after!r}")
        else:
            lines.append("  changes: none")
        return "\n".join(lines)


CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\ufeff\u2060]")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

_LONG_VOWEL = re.compile(r"([aeiou])\1+")


def fold_romanisation(text: str) -> str:
    """Collapse long vowels so one glossary key covers every spelling of a word."""
    return _LONG_VOWEL.sub(r"\1", text.lower())


class Normaliser:
    """Loads the lexicon once and applies the five steps in order."""

    def __init__(self, path: str | Path = LEXICON_FILE):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.abbreviations = {k.lower(): v for k, v in data["abbreviations"].items()}
        self.glossary = {k.lower(): v for k, v in data["glossary"].items()
                         if not k.startswith("_")}
        self.vocabulary = {w.lower() for w in data["vocabulary"]}
        self._phrases = sorted(self.glossary, key=lambda k: (-len(k.split()), -len(k)))
        self._patterns = {p: self._vowel_tolerant_pattern(p) for p in self._phrases}
        self._protected = (self.vocabulary | set(self.abbreviations)
                           | {w for k in self.glossary for w in k.split()}
                           | {w for v in self.glossary.values() for w in v.split()})

    @staticmethod
    def _vowel_tolerant_pattern(phrase: str) -> re.Pattern:
        """A key like `pani` compiled to match pani / paani / paanii."""
        folded = fold_romanisation(phrase)
        parts = []
        for ch in folded:
            if ch in "aeiou":
                parts.append(ch + "+")
            elif ch == " ":
                parts.append(r"\s+")
            else:
                parts.append(re.escape(ch))
        return re.compile(r"\b" + "".join(parts) + r"\b", re.IGNORECASE)

    def _unicode(self, text: str, changes: list[Change]) -> str:
        out = unicodedata.normalize("NFKC", text)
        out = CONTROL.sub("", out)
        out = " ".join(out.split())
        if out != text:
            changes.append(Change("unicode", text[:60], out[:60]))
        return out

    def _transliterate(self, text: str, changes: list[Change]) -> str:
        scripts = detect_scripts(text)
        if not ({"devanagari", "bengali"} & set(scripts)):
            return text
        out = transliterate(text)
        if out != text:
            changes.append(Change("transliterate", text, out))
        return out

    def _abbreviations(self, text: str, changes: list[Change]) -> str:
        def sub(m: re.Match) -> str:
            word = m.group(0)
            expansion = self.abbreviations.get(word.lower().strip("."))
            if expansion is None:
                return word
            changes.append(Change("abbreviation", word, expansion))
            return expansion

        return re.sub(r"\b[A-Za-z][A-Za-z0-9]{1,7}\.?\b", sub, text)

    def _glossary(self, text: str, changes: list[Change]) -> str:
        """Longest phrase first, matched on the vowel-folded form."""
        for phrase in self._phrases:
            pattern = self._patterns[phrase]
            found = pattern.findall(text)
            if not found:
                continue
            replacement = self.glossary[phrase]
            hit = found[0] if isinstance(found[0], str) else found[0][0]
            if hit.lower() == replacement.lower():
                continue
            text = pattern.sub(replacement, text)
            changes.append(Change("glossary", hit, replacement))
        return text

    def _typos(self, text: str, changes: list[Change]) -> str:
        def sub(m: re.Match) -> str:
            word = m.group(0)
            low = word.lower()
            if len(low) < 5 or low in self._protected:
                return word
            hits = [v for v in self.vocabulary
                    if abs(len(v) - len(low)) <= 1 and edit_distance_at_most_1(low, v)]
            if len(hits) != 1:
                return word
            changes.append(Change("typo", word, hits[0]))
            return hits[0]

        return WORD.sub(sub, text)

    def __call__(self, text: str) -> Normalised:
        original = text
        changes: list[Change] = []
        scripts = detect_scripts(text)

        out = self._unicode(text, changes)
        out = self._transliterate(out, changes)
        out = self._abbreviations(out, changes)
        out = self._glossary(out, changes)
        out = self._typos(out, changes)

        return Normalised(text=out, original=original, scripts=scripts, changes=changes)


_NORMALISER: Normaliser | None = None


def get_normaliser() -> Normaliser:
    global _NORMALISER
    if _NORMALISER is None:
        _NORMALISER = Normaliser()
    return _NORMALISER


def normalise(text: str) -> Normalised:
    return get_normaliser()(text)


LOG_PATTERNS = [
    re.compile(r"^\[?(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?)\]?\s*[|\-]?\s*"
               r"\[?(?P<site>[A-Za-z0-9_.\-]{2,40})\]?\s*[|\-:]\s*(?P<text>.+)$"),
    re.compile(r"^\[?(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?)\]?\s*[|\-:]?\s*"
               r"(?P<text>.+)$"),
    re.compile(r"^\[?(?P<site>[A-Za-z0-9_.\-]{2,40})\]?\s*[|]\s*(?P<text>.+)$"),
]


@dataclass
class Record:
    narrative: str
    site_id: str | None = None
    timestamp: datetime | None = None
    source: str = ""
    normalised: Normalised | None = None

    def to_dict(self) -> dict:
        return {
            "narrative": self.narrative,
            "site_id": self.site_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source": self.source,
            "normalisation": self.normalised.to_dict() if self.normalised else None,
        }


def _parse_ts(raw: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_log_line(line: str, default_site: str | None = None) -> Record | None:
    """One shift-log line to a record. Returns None for blanks and comments."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    for pattern in LOG_PATTERNS:
        m = pattern.match(line)
        if m:
            groups = m.groupdict()
            return Record(
                narrative=groups["text"].strip(),
                site_id=(groups.get("site") or default_site),
                timestamp=_parse_ts(groups["ts"]) if groups.get("ts") else None,
                source="log",
            )
    return Record(narrative=line, site_id=default_site, source="log:unparsed")


def read_records(path: Path, text_col: str | None = None, site_col: str | None = None,
                 time_col: str | None = None, default_site: str | None = None
                 ) -> list[Record]:
    """CSV, JSONL or a plain log, decided by suffix."""
    suffix = path.suffix.lower()

    if suffix in (".csv", ".tsv"):
        import pandas as pd

        df = pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
        col = text_col or next(
            (c for c in ("narrative_text", "narrative", "description", "text", "report")
             if c in df.columns), df.columns[0])
        out = []
        for _, row in df.iterrows():
            ts = _parse_ts(str(row[time_col])) if time_col and time_col in df else None
            out.append(Record(
                narrative=str(row[col]),
                site_id=(str(row[site_col]) if site_col and site_col in df else default_site),
                timestamp=ts, source=f"csv:{col}",
            ))
        return out

    if suffix in (".jsonl", ".ndjson"):
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            col = text_col or next(
                (c for c in ("narrative_text", "narrative", "description", "text")
                 if c in row), None)
            if col is None:
                continue
            raw_ts = row.get(time_col or "timestamp")
            out.append(Record(
                narrative=str(row[col]),
                site_id=str(row.get(site_col or "site_id", default_site or "") or "") or None,
                timestamp=_parse_ts(str(raw_ts)) if raw_ts else None,
                source="jsonl",
            ))
        return out

    return [r for r in (parse_log_line(l, default_site)
                        for l in path.read_text(encoding="utf-8").splitlines())
            if r is not None]


def ingest(records: list[Record]) -> list[Record]:
    """Normalise in place and return the same list, for chaining."""
    norm = get_normaliser()
    for r in records:
        r.normalised = norm(r.narrative)
        r.narrative = r.normalised.text
    return records


PROBE_PAIRS: list[tuple[str, str, str]] = [
    ("hinglish",
     "A worker fell from the scaffold because the permit to work had not been issued.",
     "Majdoor machan se gir gaya kyunki PTW issue nahi tha."),
    ("hinglish",
     "The worker received an electric shock while repairing the pump without isolation.",
     "Pump ki marammat karte samay majdoor ko current lag gaya, isolation nahi tha."),
    ("devanagari",
     "There was a fire near the tank and smoke spread across the area.",
     "टंकी के पास आग लग गयी और धुआं फैल गया।"),
    ("assamese",
     "A worker was injured when he fell from the ladder.",
     "শ্ৰমিক এজন খহি পৰি আঘাত পালে।"),
    ("abbrev",
     "The permit to work and job safety analysis were not completed before hot work "
     "began, and the lower explosive limit meter was not calibrated.",
     "PTW and JSA not done before HW started, LEL meter not calibrated."),
    ("abbrev",
     "Hydrogen sulphide alarm sounded and the crew had no self contained breathing "
     "apparatus at the gas collecting station.",
     "H2S alarm sounded, crew had no SCBA at the GCS."),
    ("typos",
     "The scaffold platform handrail was missing and the worker had no harness.",
     "The scaffld platfrom handrai was missing and the worker had no harnes."),
    ("typos",
     "A pressure vessel flange was opened before the isolation was confirmed.",
     "A presure vesel flang was opened before the isolaton was confirmed."),
    ("mixed",
     "The contractor was working at height without a harness and fell to the deck.",
     "Thekedar WAH kar raha tha bina belt ke, aur deck par gir gaya."),
    ("mixed",
     "A gas leak was found near the wellhead and work was stopped immediately.",
     "Wellhead ke paas gaas leek mila, kaam turant band kar diya."),
]


def run_probe(scorer=None) -> dict:
    """Score each pair raw and normalised; report whether the gap closed."""
    import numpy as np

    if scorer is None:
        from ml.predict import Scorer

        scorer = Scorer()

    clean = [c for _, c, _ in PROBE_PAIRS]
    noisy = [n for _, _, n in PROBE_PAIRS]
    fixed = [normalise(n).text for n in noisy]

    s_clean = np.asarray(scorer(clean), dtype=float)
    s_noisy = np.asarray(scorer(noisy), dtype=float)
    s_fixed = np.asarray(scorer(fixed), dtype=float)

    gap_raw = np.abs(s_noisy - s_clean)
    gap_norm = np.abs(s_fixed - s_clean)

    def spearman(a, b):
        ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
        ra, rb = ra - ra.mean(), rb - rb.mean()
        denom = np.sqrt((ra**2).sum() * (rb**2).sum())
        return float((ra * rb).sum() / denom) if denom else float("nan")

    rng = np.random.default_rng(0)
    delta = gap_raw - gap_norm
    draws = rng.integers(0, len(delta), size=(10000, len(delta)))
    boot = delta[draws].mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])

    return {
        "n_pairs": len(PROBE_PAIRS),
        "mean_gap_raw": float(gap_raw.mean()),
        "mean_gap_normalised": float(gap_norm.mean()),
        "mean_gap_reduction": float(delta.mean()),
        "gap_reduction_ci95": [float(lo), float(hi)],
        "gap_reduction_resolvable": bool(lo > 0),
        "max_gap_raw": float(gap_raw.max()),
        "max_gap_normalised": float(gap_norm.max()),
        "pairs_improved": int((gap_norm < gap_raw).sum()),
        "pairs_worsened": int((gap_norm > gap_raw).sum()),
        "spearman_raw_vs_clean": spearman(s_noisy, s_clean),
        "spearman_normalised_vs_clean": spearman(s_fixed, s_clean),
        "rows": [
            {"kind": k, "clean": round(float(c), 4), "noisy": round(float(nz), 4),
             "normalised": round(float(f), 4),
             "gap_raw": round(float(gr), 4), "gap_norm": round(float(gn), 4),
             "text_normalised": ft}
            for (k, _, _), c, nz, f, gr, gn, ft
            in zip(PROBE_PAIRS, s_clean, s_noisy, s_fixed, gap_raw, gap_norm, fixed)
        ],
    }


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    ap = argparse.ArgumentParser(
        description="Normalise raw field reports into something the model can read.")
    ap.add_argument("--text", help="normalise one narrative and show every step")
    ap.add_argument("--file", help="CSV, JSONL, or a shift log")
    ap.add_argument("--text-col", help="CSV/JSONL column holding the narrative")
    ap.add_argument("--site-col", help="CSV/JSONL column holding the site")
    ap.add_argument("--time-col", help="CSV/JSONL column holding the timestamp")
    ap.add_argument("--site", help="site id for records that carry none")
    ap.add_argument("--score", action="store_true", help="score after normalising")
    ap.add_argument("--record", action="store_true",
                    help="write to the observation store (implies --score)")
    ap.add_argument("--probe", action="store_true",
                    help="measure whether normalisation closes the gap to clean text")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=20, help="how many records to print")
    args = ap.parse_args()

    if args.probe:
        from ml.artifacts import ModelUnavailable

        try:
            result = run_probe()
        except ModelUnavailable as exc:
            raise SystemExit(str(exc))
        if args.json:
            print(json.dumps(result, indent=2))
            return
        print(f"\n{len(PROBE_PAIRS)} hand-written pairs: one incident, written clean "
              f"and written as it arrives.\n")
        print(f"  {'kind':<12}{'clean':>7}{'noisy':>7}{'norm':>7}"
              f"{'|gap| raw':>11}{'|gap| norm':>12}")
        print("  " + "-" * 56)
        for r in result["rows"]:
            better = "*" if r["gap_norm"] < r["gap_raw"] else " "
            print(f"  {r['kind']:<12}{r['clean']:>7.3f}{r['noisy']:>7.3f}"
                  f"{r['normalised']:>7.3f}{r['gap_raw']:>11.3f}"
                  f"{r['gap_norm']:>11.3f}{better}")
        print("  " + "-" * 56)
        print(f"  mean |gap| to clean : {result['mean_gap_raw']:.4f} raw "
              f"-> {result['mean_gap_normalised']:.4f} normalised")
        print(f"  max  |gap| to clean : {result['max_gap_raw']:.4f} raw "
              f"-> {result['max_gap_normalised']:.4f} normalised")
        print(f"  pairs closer / further: {result['pairs_improved']} / "
              f"{result['pairs_worsened']}")
        ci = result["gap_reduction_ci95"]
        verdict = "resolvable" if result["gap_reduction_resolvable"] else "NOT resolvable"
        print(f"  gap reduction       : {result['mean_gap_reduction']:+.4f} "
              f"95% CI [{ci[0]:+.4f}, {ci[1]:+.4f}] -- {verdict} on "
              f"{result['n_pairs']} pairs")
        print(f"  Spearman vs clean order: {result['spearman_raw_vs_clean']:.3f} raw "
              f"-> {result['spearman_normalised_vs_clean']:.3f} normalised")
        print("\n  Hand-written probes, not a benchmark. No public corpus of Assamese")
        print("  oilfield reports exists to test against. docs/RESULTS.md section 5g.")
        return

    if args.text:
        n = normalise(args.text)
        print(json.dumps(n.to_dict(), indent=2, ensure_ascii=False)
              if args.json else "\n" + n.describe())
        if args.score:
            from ml.predict import Scorer

            s = Scorer()
            print(f"\n  score raw        : {float(s([args.text])[0]):.4f}")
            print(f"  score normalised : {float(s([n.text])[0]):.4f}")
        return

    if not args.file:
        raise SystemExit("Nothing to do. Pass --text, --file or --probe.")

    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"{path} does not exist")
    records = ingest(read_records(path, args.text_col, args.site_col, args.time_col,
                                  args.site))
    if not records:
        raise SystemExit(f"No records parsed from {path}")

    scores = None
    if args.score or args.record:
        from ml.artifacts import ModelUnavailable

        try:
            from ml.predict import Scorer

            scorer = Scorer()
        except ModelUnavailable as exc:
            raise SystemExit(str(exc))
        scores = [float(p) for p in scorer([r.narrative for r in records])]

    if args.record:
        from ml.rules import get_matcher
        from ml.store import Store

        matcher = get_matcher()
        rows = [dict(site_id=r.site_id or "unknown", narrative=r.narrative,
                     sif_probability=p, timestamp=r.timestamp,
                     rules=[m.rule_id for m in matcher.match(r.narrative).matched_rules[:2]],
                     model="ingest")
                for r, p in zip(records, scores)]
        with Store() as store:
            ids = store.record_many(rows)
        print(f"recorded {len(ids)} observations "
              f"across {len({r.site_id or 'unknown' for r in records})} site(s)")

    if args.json:
        payload = [r.to_dict() for r in records]
        if scores:
            for row, p in zip(payload, scores):
                row["sif_probability"] = round(p, 4)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    changed = sum(1 for r in records if r.normalised and r.normalised.modified)
    print(f"\n{len(records)} record(s) from {path.name}; "
          f"{changed} changed by normalisation\n")
    for i, r in enumerate(records[: args.limit]):
        head = f"[{i}]"
        if r.site_id:
            head += f" site={r.site_id}"
        if r.timestamp:
            head += f" at={r.timestamp:%Y-%m-%d %H:%M}"
        if scores:
            head += f" score={scores[i]:.3f}"
        print(head)
        print(r.normalised.describe() if r.normalised else f"  {r.narrative}")
        print()
    if len(records) > args.limit:
        print(f"... and {len(records) - args.limit} more")


if __name__ == "__main__":
    main()
