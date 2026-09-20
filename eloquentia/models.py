"""Structures de donnees du pipeline.

Tout ce qui sort du pipeline est serialisable en JSON : c'est ce qui sera
stocke en base cote plateforme, et ce qui alimente les courbes de progression.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Transcription
# --------------------------------------------------------------------------

class Word(BaseModel):
    """Un mot horodate. Les timestamps sont la matiere premiere des metriques
    de debit et de pauses : sans eux, aucune mesure de diction n'est possible."""

    text: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


class Transcript(BaseModel):
    text: str
    words: list[Word] = Field(default_factory=list)
    language: str = "fr"
    duration_s: float = 0.0
    provider: str = "unknown"
    model: str = "unknown"

    @property
    def has_timestamps(self) -> bool:
        return len(self.words) >= 2


# --------------------------------------------------------------------------
# Metriques calculees par le code (deterministes)
# --------------------------------------------------------------------------

class FillerHit(BaseModel):
    """Un tic de langage detecte."""

    pattern: str          # forme canonique, ex. "du coup"
    count: int
    examples_at: list[float] = Field(default_factory=list)  # timestamps, max 5


class PauseStats(BaseModel):
    count_short: int = 0        # 0.6 s - 1.5 s : respiration normale
    count_long: int = 0         # > 1.5 s : trou, hesitation, perte du fil
    longest_s: float = 0.0
    longest_at: float = 0.0
    total_silence_s: float = 0.0
    silence_ratio: float = 0.0  # silence / duree totale


class ProsodyStats(BaseModel):
    """Mesures issues du signal audio. Optionnel : absent si l'audio n'est pas
    exploitable (format non supporte) — le reste du pipeline continue."""

    median_f0_hz: float
    pitch_variation_st: float   # ecart-type de la hauteur en demi-tons
    energy_variation: float     # coefficient de variation de l'energie RMS
    voiced_ratio: float
    monotony_flag: bool         # True si la voix est objectivement plate


class SpeechMetrics(BaseModel):
    """Tout ce que le code mesure sans jamais demander son avis a un LLM.

    Ces valeurs sont reproductibles a l'identique : c'est ce qui rend le suivi
    de progression credible dans le temps.
    """

    duration_s: float
    speaking_time_s: float
    word_count: int

    # Part du temps imparti réellement occupée. Tenir le temps fait partie de
    # l'exercice : s'arrêter à mi-parcours est un défaut, pas une neutralité.
    time_limit_s: int = 0
    time_usage_ratio: float = 0.0

    overall_wpm: float          # mots / duree totale
    articulation_wpm: float     # mots / temps de parole effectif (hors pauses)

    pauses: PauseStats
    fillers: list[FillerHit] = Field(default_factory=list)
    filler_count: int = 0
    filler_per_min: float = 0.0

    ttr: float = 0.0            # type-token ratio brut (sensible a la longueur)
    mattr: float = 0.0          # TTR a fenetre glissante : comparable entre sessions
    immediate_repeats: int = 0
    overused_words: list[tuple[str, int]] = Field(default_factory=list)

    sentence_count: int = 0
    avg_sentence_words: float = 0.0

    prosody: ProsodyStats | None = None

    fluency_score: int = 0      # 0-100, calcule par formule figee
    fluency_notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Jugement du LLM
# --------------------------------------------------------------------------

AxisName = Literal["structure", "pertinence", "contenu", "langue", "impact"]


class AxisScore(BaseModel):
    score: int = Field(ge=0, le=100)
    justification: str


class LlmAnalysis(BaseModel):
    """Le LLM ne note que ce qu'il peut reellement juger : le fond et la forme
    du discours. Le debit, les pauses et les tics lui sont fournis comme des
    faits deja mesures — il ne les re-note pas."""

    axes: dict[AxisName, AxisScore]
    point_fort: str
    axe_prioritaire: str
    exercice: str
    reformulation: str = ""     # une phrase du discours, reecrite en mieux
    model: str = "unknown"
    # Version de la grille. Deux scores issus de grilles differentes ne sont
    # pas comparables : ne jamais les tracer sur la meme courbe.
    rubric_version: str = "1.0"


# --------------------------------------------------------------------------
# Rapport final
# --------------------------------------------------------------------------

class Report(BaseModel):
    session_id: str
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    domain: str
    topic: str
    time_limit_s: int

    transcript: Transcript
    metrics: SpeechMetrics
    analysis: LlmAnalysis

    global_score: int = 0

    def scores_flat(self) -> dict[str, int]:
        """Vue plate des scores, pour les courbes de progression."""
        out = {"global": self.global_score, "aisance": self.metrics.fluency_score}
        out.update({name: axis.score for name, axis in self.analysis.axes.items()})
        return out
