"""Tests de la banque de sujets et du tirage."""

from __future__ import annotations

import random

import pytest

from eloquentia.topics import (
    DOMAINS,
    DOMAINS_BY_KEY,
    resource_payload,
    suggest_resources,
    draw,
    draw_domain,
    draw_topic,
    wheel_payload,
)


def test_banque_non_vide_et_sans_doublon():
    assert len(DOMAINS) >= 8
    tous = [t for d in DOMAINS for t in d.topics]
    assert len(tous) >= 80
    assert len(set(tous)) == len(tous), "un sujet apparaît dans deux domaines"


def test_chaque_domaine_a_de_quoi_tirer():
    for d in DOMAINS:
        assert len(d.topics) >= 8, f"{d.key} : trop peu de sujets"


def test_cles_uniques():
    assert len(DOMAINS_BY_KEY) == len(DOMAINS)


def test_tirage_evite_les_domaines_recents():
    exclus = [d.key for d in DOMAINS[:-1]]
    domain = draw_domain(exclude=exclus, rng=random.Random(0))
    assert domain.key == DOMAINS[-1].key


def test_tirage_ne_casse_pas_si_tout_est_exclu():
    """Après beaucoup de sessions, tout peut être dans l'historique récent :
    le tirage doit repartir du pool complet, pas lever une exception."""
    domain = draw_domain(exclude=[d.key for d in DOMAINS], rng=random.Random(0))
    assert domain in DOMAINS

    d = DOMAINS[0]
    assert draw_topic(d, exclude=list(d.topics), rng=random.Random(0)) in d.topics


def test_filtre_par_niveau():
    d = draw_domain(level="echauffement", rng=random.Random(1))
    assert d.level == "echauffement"


def test_tirage_complet_coherent():
    domain, topic = draw(rng=random.Random(42))
    assert topic in domain.topics


def test_tirage_reproductible_a_graine_fixe():
    a = draw(rng=random.Random(7))
    b = draw(rng=random.Random(7))
    assert a == b


def test_payload_roue():
    payload = wheel_payload()
    assert len(payload) == len(DOMAINS)
    assert all(p["color"].startswith("#") for p in payload)
    assert all(p["topic_count"] > 0 for p in payload)


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.key)
def test_sujets_bien_formes(domain):
    for topic in domain.topics:
        assert topic == topic.strip()
        assert len(topic) > 15, f"sujet trop court : {topic}"
        assert topic[-1] in ".?!", f"ponctuation finale manquante : {topic}"


# --------------------------------------------------------------------------
# Ressources
# --------------------------------------------------------------------------

def test_chaque_domaine_a_des_ressources():
    for d in DOMAINS:
        assert len(d.resources) >= 4, f"{d.key} : trop peu de ressources"


def test_ressources_bien_formees():
    for d in DOMAINS:
        for r in d.resources:
            assert r.title and r.author and r.note
            # Pas d'URL : un lien meurt, et une adresse inventee est pire
            # qu'absente. L'interface fabrique un lien de recherche.
            assert "http" not in r.title + r.author + r.note


def test_suggestion_limitee_et_issue_du_domaine():
    d = DOMAINS_BY_KEY["education"]
    choisies = suggest_resources(d, "Doit-on apprendre par coeur ?", limit=3)
    assert len(choisies) == 3
    assert all(r in d.resources for r in choisies)


def test_suggestion_rapproche_du_sujet():
    """Le rapprochement doit remonter la ressource qui parle du sujet, pas la
    premiere de la liste."""
    d = DOMAINS_BY_KEY["education"]
    top = suggest_resources(d, "Doit-on apprendre par coeur ?", limit=1)[0]
    assert "Dehaene" in top.author

    d = DOMAINS_BY_KEY["afrique"]
    top = suggest_resources(d, "Partir est-il une trahison ?", limit=1)[0]
    assert top.title == "Petit pays"


def test_suggestion_sur_sujet_sans_mot_commun():
    """Aucun mot partage : on renvoie quand meme des pistes du domaine plutot
    qu'une liste vide."""
    d = DOMAINS_BY_KEY["sciences"]
    assert len(suggest_resources(d, "Zzz qqq xyz ?", limit=3)) == 3


def test_payload_ressource():
    r = DOMAINS_BY_KEY["arts"].resources[0]
    p = resource_payload(r)
    assert p["search"] == f"{r.title} {r.author}"
    assert set(p) == {"kind", "title", "author", "note", "search"}


def test_ligature_et_graphie_simple_se_rejoignent():
    """« coeur » saisi sans ligature doit retrouver les memes ressources que
    « coeur » avec la ligature."""
    d = DOMAINS_BY_KEY["education"]
    avec = suggest_resources(d, "Doit-on apprendre par cœur ?", limit=2)
    sans = suggest_resources(d, "Doit-on apprendre par coeur ?", limit=2)
    assert [r.title for r in avec] == [r.title for r in sans]
