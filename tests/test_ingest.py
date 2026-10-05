"""The ingestion pipeline."""

from __future__ import annotations

from datetime import timezone

import pytest

from ml.ingest import (
    Normaliser,
    delete_final_schwa,
    detect_scripts,
    edit_distance_at_most_1,
    fold_romanisation,
    normalise,
    parse_log_line,
    read_records,
    transliterate,
)


@pytest.fixture(scope="module")
def norm():
    return Normaliser()


def test_zero_width_and_control_characters_are_stripped(norm):
    n = norm("worker​ fell from the‎ scaffold")
    assert "​" not in n.text and "‎" not in n.text
    assert n.text == "worker fell from the scaffold"


def test_whitespace_is_collapsed(norm):
    assert norm("worker   fell\n\nfrom  the ladder").text == \
        "worker fell from the ladder"


def test_clean_english_is_left_alone(norm):
    text = "A scaffold plank moved underfoot as a fitter stepped onto it."
    n = norm(text)
    assert n.text == text
    assert not n.modified
    assert n.changes == []


def test_detects_the_scripts_present():
    assert detect_scripts("worker fell") == ["latin"]
    assert "devanagari" in detect_scripts("आग")
    assert "bengali" in detect_scripts("শ্ৰমিক")
    assert set(detect_scripts("worker ne आग dekhi")) >= {"latin", "devanagari"}


def test_devanagari_becomes_latin():
    assert transliterate("आग") == "aag"
    assert transliterate("पास") == "paas"


def test_bengali_assamese_becomes_latin():
    assert transliterate("শ্ৰমিক") == "shramik"
    assert transliterate("আঘাত") == "aaghaat"


def test_conjuncts_drop_the_inherent_vowel():
    """A virama joins consonants: শ্ৰ is `shr`, never `shara`."""
    assert transliterate("শ্ৰমিক").startswith("shr")


def test_final_schwa_is_deleted():
    """Without this the glossary never matches transliterated text at all."""
    assert delete_final_schwa("aaga") == "aag"
    assert delete_final_schwa("shramika") == "shramik"
    assert delete_final_schwa("gayaa") == "gayaa", "a real long vowel must survive"
    assert delete_final_schwa("ke") == "ke"
    assert delete_final_schwa("na") == "na", "too short to strip"


def test_transliteration_leaves_latin_and_punctuation_alone():
    assert transliterate("worker fell, 8 metres.") == "worker fell, 8 metres."


def test_danda_becomes_a_full_stop():
    assert transliterate("आग।").endswith(".")


def test_indic_digits_become_arabic():
    assert transliterate("८") == "8"
    assert transliterate("৮") == "8"


def test_folding_collapses_long_vowels():
    assert fold_romanisation("paani") == "pani"
    assert fold_romanisation("paanii") == "pani"
    assert fold_romanisation("gayaa") == "gaya"


def test_one_lexicon_entry_covers_every_spelling(norm):
    """Romanisation is not standardised; the lexicon must not need every variant."""
    for spelling in ("pani", "paani", "paanii"):
        assert "water" in norm(f"{spelling} leaked onto the deck").text.lower()


def test_abbreviations_expand(norm):
    n = norm("PTW and JSA not done before HW started")
    assert "permit to work" in n.text
    assert "job safety analysis" in n.text
    assert "work at height" not in n.text
    assert "hot work" in n.text


def test_abbreviations_with_digits_expand(norm):
    assert "hydrogen sulphide" in norm("H2S alarm sounded").text


def test_abbreviation_expansion_is_case_insensitive(norm):
    assert "permit to work" in norm("ptw was not raised").text


def test_ordinary_words_are_not_treated_as_abbreviations(norm):
    text = "The worker was near the pump and the valve"
    assert norm(text).text == text


def test_romanised_hindi_becomes_english(norm):
    n = norm("Majdoor machan se gir gaya")
    assert "worker" in n.text and "scaffold" in n.text and "fell" in n.text
    assert "majdoor" not in n.text.lower()


def test_longer_phrases_win_over_their_own_prefixes(norm):
    """`gir gaya` must beat `gira`, or the phrase entry is dead."""
    n = norm("worker gir gaya from the ladder")
    assert "fell" in n.text
    assert "gir" not in n.text.lower()


def test_devanagari_reaches_the_glossary_after_transliteration(norm):
    """The end-to-end path that was silently broken: script -> latin -> English."""
    n = norm("टंकी के पास आग लग गयी")
    assert "caught fire" in n.text
    assert "tank" in n.text
    steps = {c.step for c in n.changes}
    assert {"transliterate", "glossary"} <= steps


def test_assamese_reaches_the_glossary_after_transliteration(norm):
    n = norm("শ্ৰমিক আঘাত পালে")
    assert "worker" in n.text and "injury" in n.text


def test_identity_entries_are_not_logged_as_changes(norm):
    """`gaas` -> `gas` is a change; `gas` -> `gas` is noise in an audit trail."""
    n = norm("gas leak near the wellhead")
    assert not [c for c in n.changes if c.before.lower() == c.after.lower()]


def test_edit_distance_recognises_one_edit():
    assert edit_distance_at_most_1("scaffold", "scaffold")
    assert edit_distance_at_most_1("scaffld", "scaffold")
    assert edit_distance_at_most_1("platfrom", "platform")
    assert edit_distance_at_most_1("harnes", "harness")
    assert not edit_distance_at_most_1("presure vesel", "pressure vessel")
    assert not edit_distance_at_most_1("cat", "dog")


def test_domain_typos_are_repaired(norm):
    n = norm("The scaffld platfrom handrai was missing")
    assert "scaffold" in n.text and "platform" in n.text and "handrail" in n.text


def test_short_words_are_never_corrected(norm):
    """At four letters a single edit reaches too many real words to be evidence."""
    text = "the pump was hot and the pipe was bent"
    assert norm(text).text == text


def test_words_already_in_the_lexicon_are_left_alone(norm):
    text = "The welder checked the flange and the valve before cutting"
    assert norm(text).text == text


def test_a_typo_with_two_candidates_is_left_alone(norm):
    """Ambiguity is left for the human. `monitor`/`monitors` style near-ties must"""
    n = norm("The wprker checked it")
    assert "wprker" in n.text or len([c for c in n.changes if c.step == "typo"]) <= 1


def test_typo_repair_does_not_touch_ordinary_prose(norm):
    text = "The supervisor decided the work should continue after the briefing"
    assert norm(text).text == text


def test_every_substitution_is_recorded(norm):
    n = norm("Majdoor machan se gir gaya, PTW nahi tha.")
    assert n.modified
    assert len(n.changes) >= 4
    for c in n.changes:
        assert c.step in {"unicode", "transliterate", "abbreviation", "glossary", "typo"}
        assert c.before and c.after is not None


def test_result_is_serialisable(norm):
    import json

    d = normalise("PTW nahi tha").to_dict()
    json.loads(json.dumps(d, ensure_ascii=False))
    assert d["original"] == "PTW nahi tha"
    assert d["modified"] is True


def test_normalisation_is_deterministic(norm):
    text = "Thekedar WAH kar raha tha bina belt ke, machan se gir gaya."
    assert norm(text).text == norm(text).text


def test_empty_and_whitespace_input_do_not_raise(norm):
    assert norm("").text == ""
    assert norm("   \n  ").text == ""


def test_parses_timestamp_site_and_text():
    r = parse_log_line("2026-09-01 06:30 | duliajan-rig-7 | Worker fell from height.")
    assert r.site_id == "duliajan-rig-7"
    assert r.narrative == "Worker fell from height."
    assert r.timestamp.year == 2026 and r.timestamp.tzinfo == timezone.utc


def test_parses_bracketed_iso_timestamps():
    r = parse_log_line("[2026-09-03T09:15] rig-7 : Handrail was missing.")
    assert r.timestamp.hour == 9
    assert r.narrative == "Handrail was missing."


def test_parses_a_line_with_no_site():
    r = parse_log_line("2026-09-04 11:00 - Worker at height without a harness.",
                       default_site="fallback")
    assert r.site_id == "fallback"
    assert "harness" in r.narrative


def test_unparsed_lines_are_kept_whole():
    """A parser that drops what it cannot read is how a report goes missing."""
    r = parse_log_line("Reversing truck came within a metre of a banksman.")
    assert r.narrative.startswith("Reversing truck")
    assert r.source == "log:unparsed"


def test_blank_lines_and_comments_are_skipped():
    assert parse_log_line("") is None
    assert parse_log_line("   ") is None
    assert parse_log_line("# night tour shift log") is None


def test_reads_a_log_file(tmp_path):
    p = tmp_path / "shift.log"
    p.write_text("# header\n"
                 "2026-09-01 06:30 | rig-7 | Majdoor machan se gir gaya.\n"
                 "\n"
                 "2026-09-02 14:05 | rig-7 | H2S alarm, no SCBA.\n", encoding="utf-8")
    records = read_records(p)
    assert len(records) == 2
    assert all(r.site_id == "rig-7" for r in records)


def test_reads_a_csv(tmp_path):
    p = tmp_path / "reports.csv"
    p.write_text("site,narrative_text\nrig-7,Worker fell from the scaffold\n",
                 encoding="utf-8")
    records = read_records(p, site_col="site")
    assert len(records) == 1
    assert records[0].site_id == "rig-7"
    assert "scaffold" in records[0].narrative


def test_reads_jsonl(tmp_path):
    p = tmp_path / "reports.jsonl"
    p.write_text('{"site_id":"rig-7","narrative":"PTW nahi tha",'
                 '"timestamp":"2026-09-01 06:30"}\n', encoding="utf-8")
    records = read_records(p)
    assert records[0].site_id == "rig-7"
    assert records[0].timestamp.day == 1


def test_ingest_normalises_in_place(tmp_path):
    from ml.ingest import ingest

    p = tmp_path / "shift.log"
    p.write_text("2026-09-01 06:30 | rig-7 | Majdoor machan se gir gaya.\n",
                 encoding="utf-8")
    r = ingest(read_records(p))[0]
    assert "worker" in r.narrative and "scaffold" in r.narrative
    assert r.normalised.original.startswith("Majdoor")


@pytest.mark.model
def test_probe_reports_the_comparison_honestly():
    from ml.ingest import run_probe

    result = run_probe()
    assert result["n_pairs"] == 10
    assert result["pairs_improved"] + result["pairs_worsened"] <= result["n_pairs"]
    lo, hi = result["gap_reduction_ci95"]
    assert lo <= result["mean_gap_reduction"] <= hi
    assert result["gap_reduction_resolvable"] == (lo > 0)


@pytest.mark.model
def test_normalisation_moves_typo_variants_back_onto_their_clean_twin():
    """The one case with a definite right answer: repairing a typo should"""
    from ml.ingest import run_probe

    rows = [r for r in run_probe()["rows"] if r["kind"] == "typos"]
    assert rows, "the probe set lost its typo pairs"
    for r in rows:
        assert r["gap_norm"] < 0.01
        assert r["gap_norm"] <= r["gap_raw"]
