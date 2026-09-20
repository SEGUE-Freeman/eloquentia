"""Tests des métriques déterministes.

Ces tests protègent la promesse centrale du produit : si le score bouge entre
deux sessions, c'est que l'orateur a changé, pas le code.
"""

from __future__ import annotations

import pytest

from eloquentia.metrics import (
    analyse_speech,
    compute_fluency,
    compute_pauses,
    detect_fillers,
    mattr,
    normalize,
    strip_fillers,
    tokenize,
)
from eloquentia.models import ProsodyStats, Word
from eloquentia.rubric import compute_global_score


def build_words(pairs: list[tuple[str, float, float]]) -> list[Word]:
    return [Word(text=t, start=s, end=e) for t, s, e in pairs]


# --------------------------------------------------------------------------
# Tokenisation
# --------------------------------------------------------------------------

def test_apostrophes_et_traits_union_preserves():
    tokens = tokenize("Aujourd'hui, c'est peut-être l'essentiel.")
    assert tokens == ["aujourd'hui", "c'est", "peut-etre", "l'essentiel"]


def test_apostrophe_typographique_equivaut_a_la_droite():
    assert normalize("c’est") == normalize("c'est")


def test_accents_ignores_pour_la_comparaison():
    assert normalize("Voilà") == "voila"


# --------------------------------------------------------------------------
# Tics de langage
# --------------------------------------------------------------------------

def test_detecte_hesitations_et_expressions():
    hits, total = detect_fillers([], "euh du coup je pense, en fait, voilà, euh bref")
    patterns = {h.pattern: h.count for h in hits}
    assert patterns["euh"] == 2
    assert patterns["du coup"] == 1
    assert patterns["en fait"] == 1
    assert patterns["voila"] == 1
    assert total == 5


def test_expression_multi_mots_comptee_une_seule_fois():
    """« en fait » ne doit pas être compté aussi comme deux mots isolés."""
    hits, total = detect_fillers([], "en fait en fait")
    assert total == 2
    assert [h.pattern for h in hits] == ["en fait"]


def test_timestamps_des_exemples_remontes():
    words = build_words([("euh", 1.0, 1.4), ("bon", 1.5, 1.8), ("euh", 2.0, 2.4)])
    hits, _ = detect_fillers(words, "euh bon euh")
    assert hits[0].examples_at == [1.0, 2.0]


def test_mot_ordinaire_non_compte_comme_tic():
    _, total = detect_fillers([], "la démocratie exige des citoyens informés")
    assert total == 0


# --------------------------------------------------------------------------
# Transcription nettoyée pour le LLM
# --------------------------------------------------------------------------

def test_retire_les_hesitations():
    assert strip_fillers("Euh, alors, je commence.") == "Alors, je commence."


def test_retire_les_expressions_multi_mots():
    assert strip_fillers("Du coup, je vais vous dire.") == "Je vais vous dire."


def test_recolle_la_ponctuation_orpheline():
    """Retirer « en fait, » ne doit pas laisser une virgule flottante."""
    assert strip_fillers("En fait, quand on regarde, euh, c'est clair.") == \
        "Quand on regarde, c'est clair."


def test_majuscule_restauree_en_tete_de_phrase():
    assert strip_fillers("Euh, la machine décide.").startswith("La machine")


def test_texte_sans_tic_inchange():
    propre = "La démocratie exige des citoyens informés."
    assert strip_fillers(propre) == propre


def test_le_nettoyage_supprime_bien_les_tics_comptes():
    """Cohérence entre les deux usages du même détecteur : ce qui est compté
    dans le score doit disparaître du texte envoyé au modèle."""
    brut = "Euh, du coup, en fait, la question est simple."
    _, avant = detect_fillers([], brut)
    _, apres = detect_fillers([], strip_fillers(brut))
    assert avant == 3
    assert apres == 0


def test_contenu_preserve():
    """Le nettoyage ne doit retirer que les tics, pas amputer le propos."""
    brut = "Du coup, les luddites brisaient les métiers à tisser, en fait."
    net = strip_fillers(brut)
    for mot in ("luddites", "brisaient", "métiers", "tisser"):
        assert mot in net


# --------------------------------------------------------------------------
# Pauses et débit
# --------------------------------------------------------------------------

def test_classement_des_pauses():
    words = build_words([
        ("un", 0.0, 0.3),
        ("deux", 0.4, 0.7),    # micro-coupure 0.1 s : ignorée
        ("trois", 1.5, 1.8),   # 0.8 s : pause courte
        ("quatre", 4.0, 4.3),  # 2.2 s : pause longue
    ])
    stats, speaking = compute_pauses(words, duration_s=5.0)

    assert stats.count_short == 1
    assert stats.count_long == 1
    assert stats.longest_s == pytest.approx(2.2, abs=0.01)
    assert stats.longest_at == pytest.approx(1.8, abs=0.01)
    assert speaking < 5.0


def test_blancs_de_debut_et_de_fin_comptes_dans_le_silence():
    words = build_words([("un", 2.0, 2.3), ("deux", 2.4, 2.7)])
    stats, _ = compute_pauses(words, duration_s=6.0)
    # 2 s avant le premier mot + 3.3 s après le dernier.
    assert stats.total_silence_s == pytest.approx(5.3, abs=0.01)


def test_debit_articulation_superieur_au_debit_global():
    """Le débit d'articulation exclut les silences : il est toujours plus
    élevé dès qu'il y a des pauses, et c'est lui qui décrit la diction."""
    words = build_words([(f"m{i}", i * 1.0, i * 1.0 + 0.3) for i in range(20)])
    metrics = analyse_speech("m0. " + " ".join(f"m{i}" for i in range(1, 20)),
                             words, duration_s=20.0)
    assert metrics.articulation_wpm > metrics.overall_wpm


# --------------------------------------------------------------------------
# Richesse lexicale
# --------------------------------------------------------------------------

def test_mattr_insensible_a_la_longueur():
    """Le TTR brut s'effondre quand le texte s'allonge, ce qui simulerait une
    régression de l'orateur. Le MATTR doit rester stable."""
    motif = [f"mot{i}" for i in range(60)]
    court = motif * 2
    long = motif * 10

    ttr_court = len(set(court)) / len(court)
    ttr_long = len(set(long)) / len(long)
    assert ttr_court - ttr_long > 0.3  # le biais existe bien

    assert mattr(court) == pytest.approx(mattr(long), abs=0.02)


def test_mattr_distingue_vocabulaire_pauvre_et_riche():
    pauvre = ["chose"] * 200
    riche = [f"mot{i}" for i in range(200)]
    assert mattr(pauvre) < 0.2
    assert mattr(riche) > 0.9


# --------------------------------------------------------------------------
# Score d'aisance
# --------------------------------------------------------------------------

BASE = dict(
    articulation_wpm=155.0,
    filler_per_min=1.0,
    long_pause_per_min=0.2,
    silence_ratio=0.18,
    mattr_value=0.75,
    prosody=None,
)


def test_reproductible():
    """La promesse du produit : deux analyses identiques donnent le même score."""
    a, _ = compute_fluency(**BASE)
    b, _ = compute_fluency(**BASE)
    assert a == b


def test_les_tics_font_baisser_le_score():
    propre, _ = compute_fluency(**BASE)
    charge, _ = compute_fluency(**{**BASE, "filler_per_min": 9.0})
    assert charge < propre - 15


def test_debit_excessif_penalise():
    normal, _ = compute_fluency(**BASE)
    presse, _ = compute_fluency(**{**BASE, "articulation_wpm": 240.0})
    lent, _ = compute_fluency(**{**BASE, "articulation_wpm": 85.0})
    assert presse < normal
    assert lent < normal


def test_monotonie_penalisee_quand_la_prosodie_est_disponible():
    plat = ProsodyStats(median_f0_hz=120, pitch_variation_st=0.8,
                        energy_variation=0.1, voiced_ratio=0.6, monotony_flag=True)
    vivant = ProsodyStats(median_f0_hz=120, pitch_variation_st=4.0,
                          energy_variation=0.4, voiced_ratio=0.6, monotony_flag=False)
    score_plat, notes_plat = compute_fluency(**{**BASE, "prosody": plat})
    score_vivant, _ = compute_fluency(**{**BASE, "prosody": vivant})
    assert score_plat < score_vivant
    assert any("plate" in n for n in notes_plat)


def test_score_borne_entre_0_et_100():
    pire, _ = compute_fluency(articulation_wpm=300, filler_per_min=30,
                              long_pause_per_min=10, silence_ratio=0.9,
                              mattr_value=0.1, prosody=None)
    meilleur, _ = compute_fluency(articulation_wpm=158, filler_per_min=0,
                                  long_pause_per_min=0, silence_ratio=0.18,
                                  mattr_value=0.82, prosody=None)
    assert 0 <= pire <= 100
    assert 0 <= meilleur <= 100
    assert meilleur > pire


def test_prosodie_absente_ne_fausse_pas_le_score():
    """Sans prosodie, les poids restants doivent être renormalisés, pas
    complétés par un zéro implicite."""
    sans, _ = compute_fluency(**BASE)
    bonne = ProsodyStats(median_f0_hz=120, pitch_variation_st=3.5,
                         energy_variation=0.4, voiced_ratio=0.6, monotony_flag=False)
    avec, _ = compute_fluency(**{**BASE, "prosody": bonne})
    assert abs(sans - avec) <= 3


# --------------------------------------------------------------------------
# Bout en bout
# --------------------------------------------------------------------------

def test_analyse_complete_sur_un_extrait():
    words = build_words([
        ("Euh,", 0.5, 1.1), ("la", 1.2, 1.35), ("démocratie", 1.4, 2.1),
        ("exige", 2.2, 2.6), ("des", 2.7, 2.85), ("citoyens", 2.9, 3.5),
        ("informés.", 3.6, 4.3),
    ])
    metrics = analyse_speech("Euh, la démocratie exige des citoyens informés.",
                             words, duration_s=5.0)

    assert metrics.word_count == 7
    assert metrics.filler_count == 1
    assert metrics.sentence_count == 1
    assert 0 <= metrics.fluency_score <= 100


def test_discours_vide_ne_leve_pas_d_exception():
    metrics = analyse_speech("", [], duration_s=10.0)
    assert metrics.word_count == 0
    assert metrics.fluency_score >= 0


# --------------------------------------------------------------------------
# Score global
# --------------------------------------------------------------------------

def test_score_global_pondere():
    axes = {"structure": 80, "pertinence": 80, "contenu": 80, "langue": 80, "impact": 80}
    assert compute_global_score(80, axes) == 80


def test_aisance_pese_un_quart_du_global():
    axes = {"structure": 60, "pertinence": 60, "contenu": 60, "langue": 60, "impact": 60}
    bas = compute_global_score(0, axes)
    haut = compute_global_score(100, axes)
    assert haut - bas == pytest.approx(25, abs=1)
