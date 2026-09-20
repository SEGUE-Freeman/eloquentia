"""Tests du serveur web.

Le pipeline est remplacé par un double : on teste le contrat HTTP et la
résolution des sujets, pas l'analyse — qui a ses propres tests et coûte un
appel réseau.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from eloquentia.models import AxisScore, LlmAnalysis, PauseStats, Report, SpeechMetrics, Transcript
from eloquentia.rubric import AXES
from eloquentia.topics import DOMAINS, UnknownTopic, resolve


def faux_rapport(domain: str, topic: str) -> Report:
    return Report(
        session_id="abc123", user_id="test", domain=domain, topic=topic,
        time_limit_s=120,
        transcript=Transcript(text="Un discours.", duration_s=60.0),
        metrics=SpeechMetrics(
            duration_s=60.0, speaking_time_s=50.0, word_count=120,
            overall_wpm=120.0, articulation_wpm=144.0, pauses=PauseStats(),
            fluency_score=70,
        ),
        analysis=LlmAnalysis(
            axes={a: AxisScore(score=60, justification="x") for a in AXES},
            point_fort="a", axe_prioritaire="b", exercice="c",
        ),
        global_score=63,
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "audio_dir", tmp_path / "audio")
    main.audio_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(main, "store", main.HistoryStore(tmp_path))

    vu = {}

    def faux_pipeline(*, audio_path, domain, topic, time_limit_s, user_id, settings):
        vu.update(domain=domain, topic=topic, user=user_id, limite=time_limit_s)
        return faux_rapport(domain, topic)

    monkeypatch.setattr(main, "analyse_session", faux_pipeline)

    c = TestClient(main.app)
    c.vu = vu
    return c


AUDIO = ("discours.webm", io.BytesIO(b"\x1a\x45\xdf\xa3" + b"0" * 5000), "audio/webm")


def envoyer(client, **champs):
    donnees = {"domain_key": "education", "topic_index": 5,
               "time_limit_s": 120, "user": "test"}
    donnees.update(champs)
    fichier = (AUDIO[0], io.BytesIO(b"\x1a\x45\xdf\xa3" + b"0" * 5000), AUDIO[2])
    return client.post("/api/sessions", files={"audio": fichier}, data=donnees)


# --------------------------------------------------------------------------
# Résolution des sujets
# --------------------------------------------------------------------------

def test_resolution_rend_le_texte_canonique():
    domaine, sujet = resolve("education", 5)
    assert domaine.label == "Éducation"
    assert sujet == "Doit-on apprendre par cœur ?"
    assert "œ" in sujet  # la ligature oe survit


def test_domaine_inconnu_rejete():
    with pytest.raises(UnknownTopic):
        resolve("inexistant", 0)


@pytest.mark.parametrize("indice", [-1, 999])
def test_indice_hors_bornes_rejete(indice):
    with pytest.raises(UnknownTopic):
        resolve("education", indice)


# --------------------------------------------------------------------------
# Contrat HTTP
# --------------------------------------------------------------------------

def test_page_servie(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Eloquentia" in r.text


def test_domaines_exposes(client):
    d = client.get("/api/domains").json()
    assert len(d) == len(DOMAINS)
    assert all(x["short"] and x["color"].startswith("#") for x in d)
    assert all(len(x["topics"]) == x["topic_count"] for x in d)


def test_tirage_renvoie_une_reference_utilisable(client):
    t = client.post("/api/draw", data={"user": "test"}).json()
    domaine, sujet = resolve(t["domain_key"], t["topic_index"])
    # La référence et le texte affiché désignent bien la même chose.
    assert sujet == t["topic"]
    assert domaine.label == t["domain"]


def test_session_utilise_le_sujet_canonique(client):
    """Régression : le client n'envoie plus le texte du sujet. Même s'il
    trichait, c'est la banque qui fait foi."""
    r = envoyer(client)
    assert r.status_code == 200
    assert client.vu["topic"] == "Doit-on apprendre par cœur ?"
    assert client.vu["domain"] == "Éducation"


def test_session_refuse_une_reference_invalide(client):
    assert envoyer(client, domain_key="pirate").status_code == 400
    assert envoyer(client, topic_index=9999).status_code == 400


def test_format_audio_refuse(client):
    fichier = ("virus.exe", io.BytesIO(b"MZ" + b"0" * 5000), "application/octet-stream")
    r = client.post("/api/sessions", files={"audio": fichier},
                    data={"domain_key": "education", "topic_index": 5})
    assert r.status_code == 400
    assert "Format audio" in r.json()["detail"]


def test_enregistrement_vide_refuse(client):
    fichier = ("vide.webm", io.BytesIO(b"x"), "audio/webm")
    r = client.post("/api/sessions", files={"audio": fichier},
                    data={"domain_key": "education", "topic_index": 5})
    assert r.status_code == 400


def test_audio_conserve_et_reecoutable(client):
    rapport = envoyer(client).json()
    assert rapport["audio_path"].endswith(".webm")
    assert client.get(f"/api/audio/{rapport['audio_path']}").status_code == 200


def test_audio_hors_dossier_refuse(client):
    """Le nom de fichier vient de l'URL : il ne doit pas permettre de sortir
    du dossier des enregistrements."""
    assert client.get("/api/audio/..%2F..%2F.env").status_code in (400, 404)


def test_historique_vide(client):
    d = client.get("/api/history/personne").json()
    assert d["total"] == 0
    assert d["courbe"] == []


def test_historique_apres_session(client):
    envoyer(client)
    d = client.get("/api/history/test").json()
    assert d["total"] == 1
    assert d["domaines_travailles"] == ["Éducation"]


def test_sante(client):
    assert client.get("/api/health").json()["domaines"] == len(DOMAINS)
