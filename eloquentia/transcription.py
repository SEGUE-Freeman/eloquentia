"""Transcription de l'enregistrement.

Le point critique n'est pas le texte, c'est l'horodatage mot à mot : sans lui,
pas de débit, pas de pauses, donc pas de mesure de diction. Tout fournisseur
retenu doit savoir le produire (`timestamp_granularities=["word"]`).
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Protocol

import requests

from .config import Settings
from .models import Transcript, Word


class TranscriptionError(RuntimeError):
    pass


class Transcriber(Protocol):
    def transcribe(self, audio_path: str | Path, language: str = "fr") -> Transcript:
        ...


class OpenAICompatibleWhisper:
    """Client pour toute API Whisper compatible OpenAI (Groq, OpenAI, Fireworks,
    Together, serveur whisper.cpp local...)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def transcribe(self, audio_path: str | Path, language: str = "fr") -> Transcript:
        path = Path(audio_path)
        if not path.exists():
            raise TranscriptionError(f"Fichier audio introuvable : {path}")
        if not self.settings.stt_api_key:
            raise TranscriptionError("ELOQ_STT_API_KEY manquante")

        url = f"{self.settings.stt_base_url.rstrip('/')}/audio/transcriptions"
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        with path.open("rb") as fh:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.settings.stt_api_key}"},
                files={"file": (path.name, fh, mime)},
                data=[
                    ("model", self.settings.stt_model),
                    ("language", language),
                    ("response_format", "verbose_json"),
                    ("timestamp_granularities[]", "word"),
                    ("timestamp_granularities[]", "segment"),
                ],
                timeout=self.settings.timeout_s,
            )

        if response.status_code >= 400:
            raise TranscriptionError(
                f"Transcription refusée ({response.status_code}) : {response.text[:300]}"
            )

        payload = response.json()
        return _parse_verbose_json(payload, self.settings.stt_model, "openai_compatible", language)


class MockTranscriber:
    """Transcription rejouée depuis un fichier JSON.

    Indispensable en développement : on itère sur les métriques et les prompts
    sans rappeler l'API à chaque fois, et les tests restent reproductibles.
    """

    def __init__(self, fixture_path: str | Path) -> None:
        self.fixture_path = Path(fixture_path)

    def transcribe(self, audio_path: str | Path, language: str = "fr") -> Transcript:
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        return _parse_verbose_json(payload, "fixture", "mock", language)


def _parse_verbose_json(
    payload: dict, model: str, provider: str, language: str
) -> Transcript:
    """Normalise les variantes de réponse : certains fournisseurs mettent les
    mots à la racine, d'autres à l'intérieur des segments."""

    words: list[Word] = []
    for w in payload.get("words") or []:
        words.append(Word(text=w.get("word") or w.get("text") or "",
                          start=float(w.get("start", 0.0)),
                          end=float(w.get("end", 0.0))))

    if not words:
        for segment in payload.get("segments") or []:
            for w in segment.get("words") or []:
                words.append(Word(text=w.get("word") or w.get("text") or "",
                                  start=float(w.get("start", 0.0)),
                                  end=float(w.get("end", 0.0))))

    text = (payload.get("text") or "").strip()
    if not text and words:
        text = " ".join(w.text for w in words)

    duration = float(payload.get("duration") or 0.0)
    if not duration and words:
        duration = words[-1].end

    return Transcript(
        text=text,
        words=words,
        language=payload.get("language") or language,
        duration_s=duration,
        provider=provider,
        model=model,
    )


def build_transcriber(settings: Settings, fixture: str | Path | None = None) -> Transcriber:
    if settings.stt_provider == "mock":
        if fixture is None:
            raise TranscriptionError("Mode mock : un fichier de fixture est requis")
        return MockTranscriber(fixture)
    return OpenAICompatibleWhisper(settings)
