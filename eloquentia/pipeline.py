"""Orchestration : enregistrement audio -> rapport exploitable.

    audio ─┬─> transcription (mots horodatés) ─┐
           │                                   ├─> métriques déterministes ─┐
           └─> prosodie (hauteur, énergie) ────┘                            │
                                                                            ├─> rapport
                          sujet imposé + métriques -> LLM (grille figée) ───┘

L'ordre compte : les métriques sont calculées AVANT l'appel au LLM, et lui sont
transmises comme faits. Le modèle interprète des mesures, il n'en invente pas.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from .analysis import build_analyst
from .config import Settings
from .metrics import analyse_speech, strip_fillers
from .models import Report, Transcript
from .prosody import analyse_prosody
from .rubric import compute_global_score
from .transcription import build_transcriber


def analyse_session(
    audio_path: str | Path,
    domain: str,
    topic: str,
    time_limit_s: int = 120,
    user_id: str = "anonyme",
    settings: Settings | None = None,
    fixture: str | Path | None = None,
    with_prosody: bool = True,
) -> Report:
    settings = settings or Settings.from_env()

    transcriber = build_transcriber(settings, fixture=fixture)
    transcript: Transcript = transcriber.transcribe(audio_path, language="fr")

    if not transcript.text.strip():
        raise ValueError("Transcription vide : enregistrement inaudible ou trop court")

    # La prosodie est un bonus : son absence ne doit jamais bloquer l'analyse.
    prosody = None
    if with_prosody and Path(audio_path).exists():
        prosody = analyse_prosody(audio_path)

    duration = transcript.duration_s or (transcript.words[-1].end if transcript.words else 0.0)
    metrics = analyse_speech(
        text=transcript.text,
        words=transcript.words,
        duration_s=duration,
        prosody=prosody,
    )

    # Le LLM juge une transcription débarrassée des tics : ceux-ci sont déjà
    # comptés dans le score d'aisance, et tant qu'ils restent visibles le modèle
    # les recommente et baisse ses notes à cause d'eux. La transcription brute
    # reste dans le rapport, c'est elle que l'orateur relit.
    analyst = build_analyst(settings)
    analysis = analyst.analyse(
        domain=domain,
        topic=topic,
        time_limit_s=time_limit_s,
        metrics=metrics,
        transcript_text=strip_fillers(transcript.text),
    )

    axis_scores = {name: axis.score for name, axis in analysis.axes.items()}

    return Report(
        session_id=uuid.uuid4().hex[:12],
        user_id=user_id,
        domain=domain,
        topic=topic,
        time_limit_s=time_limit_s,
        transcript=transcript,
        metrics=metrics,
        analysis=analysis,
        global_score=compute_global_score(metrics.fluency_score, axis_scores),
    )
