"""Historique des sessions et calcul de progression.

Stockage en JSON Lines, un fichier par utilisateur : suffisant pour valider le
pipeline, et remplaçable par une table Postgres sans toucher aux appelants —
seules les quatre fonctions publiques de ce module sont utilisées ailleurs.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Report

# Nombre de sessions récentes servant de référence pour situer une prestation.
BASELINE_WINDOW = 5


class HistoryStore:
    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir) / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        safe = "".join(c for c in user_id if c.isalnum() or c in "-_")
        return self.root / f"{safe or 'anonyme'}.jsonl"

    def save(self, report: Report) -> Path:
        path = self._path(report.user_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(report.model_dump_json() + "\n")
        return path

    def load(self, user_id: str) -> list[Report]:
        path = self._path(user_id)
        if not path.exists():
            return []
        reports: list[Report] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                reports.append(Report.model_validate_json(line))
        return sorted(reports, key=lambda r: r.created_at)


def compute_progress(history: list[Report], rubric_version: str | None = None) -> dict:
    """Situe la dernière session par rapport aux précédentes.

    Ne compare que des sessions notées avec la même version de grille : une
    évolution de la grille produit un saut de score qui n'est pas un progrès.
    """

    if not history:
        return {"sessions": 0}

    latest = history[-1]
    version = rubric_version or latest.analysis.rubric_version
    comparable = [r for r in history if r.analysis.rubric_version == version]

    if len(comparable) < 2:
        return {
            "sessions": len(comparable),
            "rubric_version": version,
            "current": latest.scores_flat(),
            "message": "Première session avec cette grille : pas encore de comparaison.",
        }

    current = comparable[-1].scores_flat()
    previous = comparable[-2].scores_flat()
    baseline_reports = comparable[-(BASELINE_WINDOW + 1):-1]

    deltas: dict[str, int] = {}
    vs_baseline: dict[str, float] = {}
    for key, value in current.items():
        if key in previous:
            deltas[key] = value - previous[key]
        values = [r.scores_flat().get(key) for r in baseline_reports]
        values = [v for v in values if v is not None]
        if values:
            vs_baseline[key] = round(value - sum(values) / len(values), 1)

    # Indicateurs bruts : eux aussi doivent bouger dans le bon sens.
    raw_trend = {
        "filler_per_min": [r.metrics.filler_per_min for r in comparable[-BASELINE_WINDOW:]],
        "articulation_wpm": [r.metrics.articulation_wpm for r in comparable[-BASELINE_WINDOW:]],
        "mattr": [r.metrics.mattr for r in comparable[-BASELINE_WINDOW:]],
        "global": [r.global_score for r in comparable[-BASELINE_WINDOW:]],
    }

    improving = [k for k, v in vs_baseline.items() if v >= 3]
    slipping = [k for k, v in vs_baseline.items() if v <= -3]

    return {
        "sessions": len(comparable),
        "rubric_version": version,
        "current": current,
        "delta_vs_previous": deltas,
        "delta_vs_baseline": vs_baseline,
        "best_global": max(r.global_score for r in comparable),
        "raw_trend": raw_trend,
        "improving": improving,
        "slipping": slipping,
    }


def export_curve(history: list[Report]) -> list[dict]:
    """Séries prêtes à tracer côté front."""
    return [
        {
            "date": r.created_at.isoformat(),
            "session_id": r.session_id,
            "domain": r.domain,
            "topic": r.topic,
            "rubric_version": r.analysis.rubric_version,
            **r.scores_flat(),
            "filler_per_min": r.metrics.filler_per_min,
            "articulation_wpm": r.metrics.articulation_wpm,
            "mattr": r.metrics.mattr,
        }
        for r in history
    ]


def dump_json(obj, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
