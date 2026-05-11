import json
import subprocess
import sys
from pathlib import Path

from creator_evolution_pulse_service import (
    PulseRequest,
    _build_subject_spec,
    _finalize_drafts,
    _focus_match_score,
    _focused_no_op_decision,
    _has_source_specificity,
    _source_sentence_issues,
    _tweet_link_subject_terms,
    run_pulse,
)


def test_pulse_service_mock_ready_contract(tmp_path):
    payload = run_pulse(
        PulseRequest(
            mode="run",
            request_id="pulse_test_ready",
            mock="ready",
            artifact_dir=tmp_path,
        )
    )

    assert payload["status"] == "ready"
    assert payload["selected_format"] == "Normal Tweet"
    assert payload["selected_lane"] == "Witty Edge"
    assert len(payload["drafts"]) >= 2
    assert payload["source_basis"]
    for draft in payload["drafts"]:
        assert draft["type"] == "pulse"
        assert not draft["text"].startswith("@")
        assert "recommended reply" not in draft["text"].lower()


def test_pulse_service_mock_noop_has_no_drafts(tmp_path):
    payload = run_pulse(
        PulseRequest(
            mode="run",
            request_id="pulse_test_noop",
            mock="noop",
            artifact_dir=tmp_path,
        )
    )

    assert payload["status"] == "no_op"
    assert payload["drafts"] == []


def test_pulse_cli_json_contract(tmp_path):
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "creator_evolution_pulse_cli.py"),
            "--mock",
            "ready",
            "--request-id",
            "pulse_cli_contract",
            "--artifact-dir",
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
        timeout=30,
        cwd=str(root),
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ready"
    assert payload["versions"]["service"]
    assert payload["selected_lane"]
    assert payload["selected_format"]
    assert payload["source_basis"]
    assert payload["quality_reports"]["accepted"] >= 2


def test_pulse_cli_source_contract_after_ready_run(tmp_path):
    root = Path(__file__).resolve().parents[1]
    ready = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "creator_evolution_pulse_cli.py"),
            "--mock",
            "ready",
            "--request-id",
            "pulse_cli_source_contract",
            "--artifact-dir",
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
        timeout=30,
        cwd=str(root),
    )
    assert ready.returncode == 0, ready.stderr

    proc = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "creator_evolution_pulse_cli.py"),
            "--mode",
            "source",
            "--artifact-dir",
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
        timeout=30,
        cwd=str(root),
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ready"
    assert payload["source_basis"]
    assert payload["request_id"] == "pulse_cli_source_contract"


def test_subject_spec_rejects_ambiguous_one_word_subject():
    spec = _build_subject_spec("Murray")

    assert spec is not None
    assert spec.ambiguous is True
    assert _focus_match_score("Jamal Murray is active tonight", spec) == 0


def test_person_subject_requires_short_full_name():
    spec = _build_subject_spec("Dane Key")

    assert spec is not None
    assert spec.required_terms == ("dane", "key")
    assert _focus_match_score("Dane Key had a back-shoulder catch.", spec) >= 1
    assert _focus_match_score("This is a key Broncos decision.", spec) == 0


def test_multi_term_subject_requires_all_meaningful_terms():
    spec = _build_subject_spec("Bo Nix ankle")

    assert spec is not None
    assert spec.required_terms == ("bo", "nix", "ankle")
    assert _focus_match_score("Bo Nix ankle timeline is the story.", spec) >= 1
    assert _focus_match_score("Generic ankle timeline for another quarterback.", spec) == 0


def test_event_subject_requires_all_core_terms_plus_event():
    spec = _build_subject_spec("Bo Nix press conference")

    assert spec is not None
    assert spec.kind == "event"
    assert _focus_match_score("Bo Nix press conference notes are live.", spec) >= 1
    assert _focus_match_score("Nix press conference notes from camp.", spec) == 0
    assert _focus_match_score("Bo Nix injury timeline from practice.", spec) == 0


def test_team_subject_allows_team_aliases_but_not_substrings():
    spec = _build_subject_spec("avalanche")

    assert spec is not None
    assert _focus_match_score("The Avs need to wake up.", spec) >= 1
    assert _focus_match_score("NEBOJSA COVIC talked to students.", spec) == 0


def test_tweet_link_subject_prefers_capitalized_person_name():
    assert _tweet_link_subject_terms("#Broncos rookie RB Jonah Coleman on adjusting to altitude") == ("jonah", "coleman")
    assert _tweet_link_subject_terms("Dane Key had an IMPRESSIVE back-shoulder catch") == ("dane", "key")


def test_tweet_link_subject_prefers_team_handle_over_sentence_fragment():
    spec = _build_subject_spec(
        "",
        source_text=(
            "I’ve spent 4 days wondering what the Counter-Punch would look like "
            "for a desperate @mnwild down 2-0. Kaprizov, Faber, Hughes & Boldy were fantastic."
        ),
    )

    assert spec is not None
    assert spec.canonical == "Minnesota Wild"
    assert "wild" in spec.required_terms
    assert _focus_match_score("Kaprizov and Faber changed the Wild counter-punch.", spec) >= 1
    assert _focus_match_score("The Wild stars have completely changed Game 3.", spec) == 0
    assert _focus_match_score("Odell Beckham Jr. training camp chatter is loud.", spec) == 0


def test_tweet_link_subject_can_use_source_author_context():
    spec = _build_subject_spec("", source_text="Big response tonight @mnwildPR")

    assert spec is not None
    assert spec.canonical == "Minnesota Wild"
    assert _focus_match_score("Kaprizov has the Wild counter-punch moving.", spec) >= 1


def test_focused_no_op_does_not_include_drafts_or_broad_message():
    payload = _focused_no_op_decision("Murray", [], [], _build_subject_spec("Murray"))

    assert payload["status"] == "no_op"
    assert "No broad/generic drafts" in payload["message"]


def test_broad_pulse_rejects_vague_denver_sports_moment():
    decision = {
        "best": {
            "topic": "broncos",
            "source_basis": [
                {
                    "text": "Denver Broncos HC Sean Payton setting standard amidst new faces joining the coaching staff",
                    "source": "twitter",
                }
            ],
        }
    }

    assert not _has_source_specificity(
        "This Denver sports moment is where the real offseason starts. The public answer matters less than every move after it...",
        decision,
        topic="broncos",
    )
    assert _has_source_specificity(
        "Sean Payton and new Broncos coaches are the actual source detail here.",
        decision,
        topic="broncos",
    )


def test_broad_pulse_finalize_requires_concrete_selected_signal_detail():
    decision = {
        "best": {
            "topic": "broncos",
            "source_basis": [
                {
                    "text": "Denver Broncos HC Sean Payton setting standard amidst new faces joining the coaching staff",
                    "source": "twitter",
                }
            ],
        }
    }
    data = {
        "option1": "This Denver sports moment is where the real offseason starts. The public answer matters less than the limits it quietly puts on every move after it...",
        "option1_pattern": "bad generic",
        "option2": "Sean Payton and the new Broncos coaches are the actual source detail here. Staff alignment is not a press release detail...",
        "option2_pattern": "specific",
    }

    drafts, quality = _finalize_drafts(data, decision, "Witty Edge", "Normal Tweet", {}, topic="broncos")

    assert all("Denver sports moment" not in draft["text"] for draft in drafts)
    assert any("Sean Payton" in draft["text"] for draft in drafts)
    assert any("too vague" in " ".join(item["issues"]) for item in quality["rejected"])


def test_malformed_source_sentence_is_not_safe_fallback_material():
    bad = (
        "Begs the question of why #Broncoscountry didn’t pursue DAVID NJOKU •TE "
        "Perhaps frivolous monies on RB Dobbins for similar compensation?! What happe"
    )

    assert _source_sentence_issues(bad)


def test_broad_pulse_does_not_post_single_malformed_fallback(tmp_path):
    payload = run_pulse(
        PulseRequest(
            mode="run",
            request_id="pulse_bad_source_regression",
            mock="ready",
            artifact_dir=tmp_path,
        )
    )

    assert payload["status"] == "ready"
    assert len(payload["drafts"]) >= 2

    decision = {
        "status": "ready",
        "best": {
            "topic": "broncos",
            "source_basis": [
                {
                    "text": (
                        "Begs the question of why #Broncoscountry didn’t pursue DAVID NJOKU •TE "
                        "Perhaps frivolous monies on RB Dobbins for similar compensation?! What happe"
                    ),
                    "source": "twitter",
                }
            ],
        },
    }
    data = {
        "option1": "This Denver sports moment is where the real offseason starts. The public answer matters less than every move after it...",
        "option2": "The public answer matters less than what this says about the next decision...",
        "option3": "This sports moment is where the public line gets interesting...",
    }

    drafts, quality = _finalize_drafts(data, decision, "Witty Edge", "Normal Tweet", {}, topic="")

    assert drafts == []
    assert quality["accepted"] == 0
    assert any("fallback source sentence" in " ".join(item["issues"]) for item in quality["rejected"])
