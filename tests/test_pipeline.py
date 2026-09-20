"""Tests du câblage du pipeline."""

from __future__ import annotations

import json

import pytest

from eloquentia.config import Settings
from eloquentia.models import AxisScore, LlmAnalysis
from eloquentia.pipeline import analyse_session
from eloquentia.rubric import AXES

TRANSCRIPTION = {
    "text": "Euh, du coup, la démocratie exige des citoyens informés.",
    "words": [
        {"word": "Euh,", "start": 0.5, "end": 1.0},
        {"word": "du", "start": 1.1, "end": 1.25},
        {"word": "coup,", "start": 1.3, "end": 1.6},
        {"word": "la", "start": 1.7, "end": 1.85},
        {"word": "démocratie", "start": 1.9, "end": 2.6},
        {"word": "exige", "start": 2.7, "end": 3.1},
        {"word": "des", "start": 3.2, "end": 3.35},
        {"word": "citoyens", "start": 3.4, "end": 4.0},
        {"word": "informés.", "start": 4.1, "end": 4.8},
    ],
    "language": "fr",
    "duration": 5.5,
}


@pytest.fixture
def fixture_path(tmp_path):
    path = tmp_path / "transcript.json"
    path.write_text(json.dumps(TRANSCRIPTION, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def capture(monkeypatch):
    """Remplace le LLM par un mouchard qui retient le texte reçu."""
    vu = {}

    class Espion:
        def analyse(self, domain, topic, time_limit_s, metrics, transcript_text):
            vu["texte"] = transcript_text
            vu["metrics"] = metrics
            return LlmAnalysis(
                axes={a: AxisScore(score=60, justification="x") for a in AXES},
                point_fort="a", axe_prioritaire="b", exercice="c",
            )

    monkeypatch.setattr("eloquentia.pipeline.build_analyst", lambda _: Espion())
    return vu


SETTINGS = Settings(stt_provider="mock", llm_provider="mock")


def test_le_llm_recoit_un_texte_sans_tics(fixture_path, capture):
    """Régression : les tics sont déjà sanctionnés par le score d'aisance.
    S'ils réapparaissent dans le texte transmis, le modèle les recommente et
    le même défaut est compté deux fois."""
    analyse_session("", "Société", "Un sujet", 120, "test",
                    settings=SETTINGS, fixture=fixture_path, with_prosody=False)

    assert "du coup" not in capture["texte"].lower()
    assert "euh" not in capture["texte"].lower()
    assert "démocratie" in capture["texte"]


def test_les_mesures_utilisent_le_texte_brut(fixture_path, capture):
    """Le nettoyage ne concerne que le LLM : les tics doivent rester comptés."""
    analyse_session("", "Société", "Un sujet", 120, "test",
                    settings=SETTINGS, fixture=fixture_path, with_prosody=False)
    assert capture["metrics"].filler_count == 2


def test_le_rapport_conserve_la_transcription_brute(fixture_path, capture):
    """C'est elle que l'orateur relit pour se réécouter."""
    report = analyse_session("", "Société", "Un sujet", 120, "test",
                             settings=SETTINGS, fixture=fixture_path, with_prosody=False)
    assert "Euh," in report.transcript.text


def test_transcription_vide_refusee(tmp_path, capture):
    vide = tmp_path / "vide.json"
    vide.write_text(json.dumps({"text": "", "words": [], "duration": 3}), encoding="utf-8")
    with pytest.raises(ValueError, match="vide"):
        analyse_session("", "Société", "Un sujet", 120, "test",
                        settings=SETTINGS, fixture=vide, with_prosody=False)
