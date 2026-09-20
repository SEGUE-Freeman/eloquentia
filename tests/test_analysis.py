"""Tests de la couche d'appel au LLM.

Le fournisseur est traité comme faillible. Ces tests vérifient qu'on réagit
correctement selon la nature de l'échec, sans jamais toucher au réseau.
"""

from __future__ import annotations

import json

import pytest

from eloquentia.analysis import (
    MAX_ATTEMPTS,
    AnalysisError,
    OpenAICompatibleAnalyst,
    PermanentError,
    TransientError,
    _extract_json,
)
from eloquentia.config import Settings
from eloquentia.models import PauseStats, SpeechMetrics
from eloquentia.rubric import AXES

METRICS = SpeechMetrics(
    duration_s=100.0, speaking_time_s=80.0, word_count=200,
    overall_wpm=120.0, articulation_wpm=150.0, pauses=PauseStats(),
    fluency_score=70,
)

REPONSE_VALIDE = json.dumps({
    "axes": {name: {"score": 70, "justification": "parce que"} for name in AXES},
    "point_fort": "un point fort",
    "axe_prioritaire": "un défaut",
    "exercice": "un exercice",
    "reformulation": "mieux dit",
}, ensure_ascii=False)


@pytest.fixture
def analyst(monkeypatch):
    # Aucune attente réelle : les tests de reprise ne doivent pas durer 30 s.
    monkeypatch.setattr("eloquentia.analysis.time.sleep", lambda _: None)
    settings = Settings(llm_provider="openai_compatible", llm_api_key="factice")
    return OpenAICompatibleAnalyst(settings)


def run(analyst):
    return analyst.analyse("Société", "Un sujet", 120, METRICS, "Le texte du discours.")


def scripted(analyst, monkeypatch, reponses):
    """Remplace l'appel réseau par une séquence de réponses ou d'exceptions."""
    appels = []

    def fake_call(messages):
        appels.append(messages)
        item = reponses[len(appels) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(analyst, "_call", fake_call)
    return appels


# --------------------------------------------------------------------------
# Extraction du JSON
# --------------------------------------------------------------------------

def test_json_nu():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_json_dans_un_bloc_de_code():
    """Beaucoup de modèles ouverts encadrent le JSON malgré la consigne."""
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_json_noye_dans_du_texte():
    assert _extract_json('Voici mon analyse :\n{"a": 1}\nVoilà.') == {"a": 1}


def test_absence_de_json_signalee():
    with pytest.raises(AnalysisError):
        _extract_json("Je ne peux pas répondre.")


# --------------------------------------------------------------------------
# Politique de reprise
# --------------------------------------------------------------------------

def test_succes_du_premier_coup(analyst, monkeypatch):
    appels = scripted(analyst, monkeypatch, [REPONSE_VALIDE])
    result = run(analyst)
    assert len(appels) == 1
    assert result.axes["structure"].score == 70


def test_erreur_definitive_non_reessayee(analyst, monkeypatch):
    """Un 403 « modèle hors de votre palier » ne changera pas au deuxième essai :
    insister ne fait que retarder le message utile."""
    appels = scripted(analyst, monkeypatch, [
        PermanentError("403 tier_not_allowed"),
        REPONSE_VALIDE,
    ])
    with pytest.raises(PermanentError):
        run(analyst)
    assert len(appels) == 1


def test_erreur_passagere_reessayee(analyst, monkeypatch):
    appels = scripted(analyst, monkeypatch, [
        TransientError("429"),
        TransientError("503"),
        REPONSE_VALIDE,
    ])
    result = run(analyst)
    assert len(appels) == 3
    assert result.point_fort == "un point fort"


def test_erreur_passagere_persistante_abandonne(analyst, monkeypatch):
    appels = scripted(analyst, monkeypatch, [TransientError("429")] * MAX_ATTEMPTS)
    with pytest.raises(AnalysisError):
        run(analyst)
    assert len(appels) == MAX_ATTEMPTS


def test_rappel_de_format_apres_reponse_illisible(analyst, monkeypatch):
    appels = scripted(analyst, monkeypatch, ["pas du json du tout", REPONSE_VALIDE])
    run(analyst)
    assert len(appels) == 2
    # Le second envoi contient le rappel, le premier non.
    assert "JSON valide" in appels[1][-1]["content"]
    assert "JSON valide" not in appels[0][-1]["content"]


def test_rappels_non_empiles(analyst, monkeypatch):
    """Le prompt est reconstruit à chaque reprise : sans cela, les rappels
    s'accumulent et finissent par noyer la consigne d'origine."""
    appels = scripted(analyst, monkeypatch, ["illisible", "encore illisible", REPONSE_VALIDE])
    run(analyst)
    # « JSON valide » figure aussi dans la consigne système : on compte le
    # rappel par sa formulation propre.
    rappels = sum(1 for m in appels[2] if m["content"].startswith("Ta réponse"))
    assert rappels == 1


def test_attente_respecte_retry_after(analyst, monkeypatch):
    attentes = []
    monkeypatch.setattr("eloquentia.analysis.time.sleep", attentes.append)
    scripted(analyst, monkeypatch, [TransientError("429", retry_after=7.0), REPONSE_VALIDE])
    run(analyst)
    assert 7.0 <= attentes[0] <= 7.5  # délai imposé + décalage aléatoire


def test_attente_exponentielle(analyst, monkeypatch):
    attentes = []
    monkeypatch.setattr("eloquentia.analysis.time.sleep", attentes.append)
    scripted(analyst, monkeypatch, [
        TransientError("429"), TransientError("429"), REPONSE_VALIDE,
    ])
    run(analyst)
    assert attentes[1] > attentes[0]


# --------------------------------------------------------------------------
# Validation de la réponse
# --------------------------------------------------------------------------

def test_axe_manquant_rejete(analyst, monkeypatch):
    incomplet = json.dumps({
        "axes": {"structure": {"score": 70, "justification": "x"}},
        "point_fort": "a", "axe_prioritaire": "b", "exercice": "c",
    })
    scripted(analyst, monkeypatch, [incomplet] * MAX_ATTEMPTS)
    with pytest.raises(AnalysisError):
        run(analyst)


def test_score_hors_bornes_ramene_dans_l_echelle(analyst, monkeypatch):
    excessif = json.loads(REPONSE_VALIDE)
    excessif["axes"]["structure"]["score"] = 150
    excessif["axes"]["langue"]["score"] = -20
    scripted(analyst, monkeypatch, [json.dumps(excessif)])
    result = run(analyst)
    assert result.axes["structure"].score == 100
    assert result.axes["langue"].score == 0


def test_score_textuel_accepte(analyst, monkeypatch):
    """Certains modèles renvoient « 72 » comme chaîne plutôt que comme entier."""
    textuel = json.loads(REPONSE_VALIDE)
    textuel["axes"]["impact"]["score"] = "72"
    scripted(analyst, monkeypatch, [json.dumps(textuel)])
    assert run(analyst).axes["impact"].score == 72


def test_cle_absente_signalee_sans_appel_reseau():
    analyst = OpenAICompatibleAnalyst(Settings(llm_provider="openai_compatible", llm_api_key=""))
    with pytest.raises(AnalysisError, match="ELOQ_LLM_API_KEY"):
        run(analyst)
