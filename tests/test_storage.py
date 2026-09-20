"""Tests de l'historique et de la progression."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from eloquentia.models import (
    AxisScore,
    LlmAnalysis,
    PauseStats,
    Report,
    SpeechMetrics,
    Transcript,
)
from eloquentia.storage import HistoryStore, compute_progress, export_curve

AXES = ("structure", "pertinence", "contenu", "langue", "impact")


def make_report(
    *, global_score: int, fluency: int = 60, axis_score: int = 60,
    rubric_version: str = "1.0", days_ago: int = 0, user: str = "test",
) -> Report:
    return Report(
        session_id=f"s{global_score}{axis_score}{rubric_version}{days_ago}",
        user_id=user,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        domain="Société",
        topic="Un sujet",
        time_limit_s=120,
        transcript=Transcript(text="texte", duration_s=100.0),
        metrics=SpeechMetrics(
            duration_s=100.0, speaking_time_s=80.0, word_count=200,
            overall_wpm=120.0, articulation_wpm=150.0, pauses=PauseStats(),
            fluency_score=fluency,
        ),
        analysis=LlmAnalysis(
            axes={a: AxisScore(score=axis_score, justification="x") for a in AXES},
            point_fort="x", axe_prioritaire="y", exercice="z",
            rubric_version=rubric_version,
        ),
        global_score=global_score,
    )


def test_sauvegarde_et_relecture(tmp_path):
    store = HistoryStore(tmp_path)
    store.save(make_report(global_score=50, days_ago=2))
    store.save(make_report(global_score=60, days_ago=0))

    history = store.load("test")
    assert len(history) == 2
    # Relu dans l'ordre chronologique, quel que soit l'ordre d'écriture.
    assert [r.global_score for r in history] == [50, 60]


def test_utilisateur_inconnu_retourne_liste_vide(tmp_path):
    assert HistoryStore(tmp_path).load("personne") == []


def test_identifiant_utilisateur_assaini(tmp_path):
    """Un identifiant venant du web ne doit pas pouvoir écrire hors du dossier."""
    store = HistoryStore(tmp_path)
    store.save(make_report(global_score=50, user="../../evil"))
    written = list((tmp_path / "sessions").glob("*.jsonl"))
    assert len(written) == 1
    assert ".." not in written[0].name


def test_progression_calcule_les_ecarts(tmp_path):
    store = HistoryStore(tmp_path)
    store.save(make_report(global_score=50, fluency=50, axis_score=50, days_ago=3))
    store.save(make_report(global_score=60, fluency=65, axis_score=60, days_ago=1))

    progress = compute_progress(store.load("test"))
    assert progress["sessions"] == 2
    assert progress["delta_vs_previous"]["aisance"] == 15
    assert progress["best_global"] == 60
    assert "aisance" in progress["improving"]


def test_grilles_differentes_non_comparees(tmp_path):
    """Changer la grille décale l'échelle : mélanger les versions afficherait
    un faux progrès. Seules les sessions de la version courante comptent."""
    store = HistoryStore(tmp_path)
    store.save(make_report(global_score=30, axis_score=30, rubric_version="0.9", days_ago=5))
    store.save(make_report(global_score=32, axis_score=32, rubric_version="0.9", days_ago=4))
    store.save(make_report(global_score=70, axis_score=70, rubric_version="1.0", days_ago=1))

    progress = compute_progress(store.load("test"))
    assert progress["rubric_version"] == "1.0"
    assert progress["sessions"] == 1
    # Une seule session comparable : aucun écart annoncé.
    assert "delta_vs_previous" not in progress


def test_premiere_session_sans_comparaison(tmp_path):
    store = HistoryStore(tmp_path)
    store.save(make_report(global_score=55))
    progress = compute_progress(store.load("test"))
    assert progress["sessions"] == 1
    assert "message" in progress


def test_historique_vide(tmp_path):
    assert compute_progress([])["sessions"] == 0


def test_export_courbe(tmp_path):
    store = HistoryStore(tmp_path)
    store.save(make_report(global_score=50, days_ago=2))
    store.save(make_report(global_score=70, days_ago=0))

    curve = export_curve(store.load("test"))
    assert [p["global"] for p in curve] == [50, 70]
    assert "filler_per_min" in curve[0]
    assert "date" in curve[0]
