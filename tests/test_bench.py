"""Tests du banc d'essai de stabilité."""

from __future__ import annotations

import pytest

from eloquentia.bench import AxisStat, BenchResult, format_result


def build(globals_: list[int], **axes: list[int]) -> BenchResult:
    return BenchResult(
        model="modele-test",
        runs=len(globals_),
        axes={nom: AxisStat(nom, scores) for nom, scores in axes.items()},
        globals=globals_,
    )


def test_statistiques_par_axe():
    stat = AxisStat("structure", [50, 60, 55])
    assert stat.mean == pytest.approx(55.0)
    assert stat.spread == 10
    assert stat.stdev > 0


def test_un_seul_releve_donne_un_ecart_nul():
    """Un seul passage n'est pas une erreur : l'écart-type est nul par
    définition, statistics.stdev lèverait une exception."""
    assert AxisStat("structure", [50]).stdev == 0.0


def test_axe_vide_ne_casse_pas():
    stat = AxisStat("structure", [])
    assert stat.mean == 0.0
    assert stat.stdev == 0.0
    assert stat.spread == 0


def test_verdict_stable():
    r = build([60, 61, 59, 60], structure=[50, 51, 49, 50])
    assert r.global_stdev < 3
    assert "stable" in r.verdict()


def test_verdict_instable():
    r = build([40, 75, 52, 68], structure=[30, 80, 45, 70])
    assert "instable" in r.verdict()
    assert "n'est pas fiable" in r.verdict()


def test_verdict_sans_releve():
    assert "aucun relevé" in build([]).verdict()


def test_axe_le_plus_instable_identifie():
    r = build([60, 62], structure=[50, 52], impact=[20, 80])
    assert r.worst_axis.name == "impact"


def test_rapport_lisible():
    r = build([60, 61], structure=[50, 51], impact=[40, 42])
    sortie = format_result(r)
    assert "modele-test" in sortie
    assert "structure" in sortie
    assert "GLOBAL" in sortie


def test_echecs_reportes():
    r = build([60], structure=[50])
    r.failures.append("429 rate limited")
    assert "429" in format_result(r)
