"""Banc d'essai : mesurer la stabilité du jugement d'un modèle.

La grille ancrée et la température 0 réduisent la dérive, elles ne
l'annulent pas — sur une infrastructure distribuée, le regroupement des
requêtes introduit une variabilité résiduelle.

Cette variabilité est le plancher de bruit du suivi de progression. Si un
modèle note la même prestation 52 puis 71, une hausse de 8 points entre deux
sessions ne prouve rien. Le seul moyen de le savoir est de repasser le même
discours plusieurs fois et de mesurer l'écart.

Sert aussi à comparer deux modèles : le moins cher suffit souvent, et ce banc
le dit avec des chiffres plutôt qu'à l'intuition.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .analysis import AnalysisError, OpenAICompatibleAnalyst
from .config import Settings
from .metrics import analyse_speech, strip_fillers
from .models import Transcript
from .rubric import AXES, compute_global_score


@dataclass
class AxisStat:
    name: str
    scores: list[int] = field(default_factory=list)

    @property
    def mean(self) -> float:
        return statistics.mean(self.scores) if self.scores else 0.0

    @property
    def stdev(self) -> float:
        # Un seul relevé : écart nul par définition, pas une erreur.
        return statistics.stdev(self.scores) if len(self.scores) > 1 else 0.0

    @property
    def spread(self) -> int:
        return max(self.scores) - min(self.scores) if self.scores else 0


@dataclass
class BenchResult:
    model: str
    runs: int
    axes: dict[str, AxisStat]
    globals: list[int]
    failures: list[str] = field(default_factory=list)

    @property
    def global_stdev(self) -> float:
        return statistics.stdev(self.globals) if len(self.globals) > 1 else 0.0

    @property
    def worst_axis(self) -> AxisStat | None:
        stats = [a for a in self.axes.values() if a.scores]
        return max(stats, key=lambda a: a.stdev) if stats else None

    def verdict(self) -> str:
        """Seuil de lisibilité : en deçà de 3 points d'écart-type sur le score
        global, une progression de 5 points est un signal ; au-delà de 6, elle
        se confond avec le bruit."""
        s = self.global_stdev
        if not self.globals:
            return "aucun relevé exploitable"
        if s < 3:
            return "stable — une progression de 5 points est interprétable"
        if s < 6:
            return "acceptable — ne rien conclure sous 10 points d'écart"
        return "instable — le suivi de progression n'est pas fiable avec ce modèle"


def run_bench(
    transcript: Transcript,
    domain: str,
    topic: str,
    time_limit_s: int,
    settings: Settings,
    runs: int = 5,
) -> BenchResult:
    metrics = analyse_speech(
        transcript.text, transcript.words, transcript.duration_s,
        time_limit_s=time_limit_s,
    )
    texte = strip_fillers(transcript.text)
    analyst = OpenAICompatibleAnalyst(settings)

    axes = {name: AxisStat(name) for name in AXES}
    globals_: list[int] = []
    failures: list[str] = []

    for _ in range(runs):
        try:
            analysis = analyst.analyse(domain, topic, time_limit_s, metrics, texte)
        except AnalysisError as exc:
            failures.append(str(exc)[:120])
            continue
        for name, axis in analysis.axes.items():
            axes[name].scores.append(axis.score)
        globals_.append(compute_global_score(
            metrics.fluency_score, {n: a.score for n, a in analysis.axes.items()}
        ))

    return BenchResult(
        model=settings.llm_model, runs=runs, axes=axes,
        globals=globals_, failures=failures,
    )


def format_result(result: BenchResult) -> str:
    lines = [
        f"\n  MODÈLE : {result.model}   ({len(result.globals)}/{result.runs} relevés)",
        f"  {'axe':<14}{'moyenne':>9}{'écart-type':>12}{'amplitude':>11}",
    ]
    for name, stat in result.axes.items():
        if stat.scores:
            lines.append(
                f"  {name:<14}{stat.mean:>9.1f}{stat.stdev:>12.1f}{stat.spread:>11}"
            )

    if result.globals:
        lines.append(
            f"  {'GLOBAL':<14}{statistics.mean(result.globals):>9.1f}"
            f"{result.global_stdev:>12.1f}{max(result.globals) - min(result.globals):>11}"
        )
        lines.append(f"\n  Verdict : {result.verdict()}")
        pire = result.worst_axis
        if pire and pire.stdev >= 5:
            lines.append(f"  Axe le plus instable : {pire.name} (±{pire.stdev:.1f})")

    for f in result.failures:
        lines.append(f"  échec : {f}")

    return "\n".join(lines)
