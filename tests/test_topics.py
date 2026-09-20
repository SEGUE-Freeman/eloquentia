"""Tests de la banque de sujets et du tirage."""

from __future__ import annotations

import random

import pytest

from eloquentia.topics import (
    DOMAINS,
    DOMAINS_BY_KEY,
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
