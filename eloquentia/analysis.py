"""Appel du LLM et validation stricte de sa réponse.

Le modèle est traité comme un service faillible : sa sortie est parsée,
validée contre le schéma, et rejouée une fois si elle est invalide. Un JSON
approximatif ne doit jamais atteindre la base de données.
"""

from __future__ import annotations

import json
import random
import re
import time

import requests
from pydantic import ValidationError

from .config import Settings
from .models import AxisScore, LlmAnalysis, SpeechMetrics
from .rubric import AXES, RUBRIC_VERSION, build_messages


class AnalysisError(RuntimeError):
    pass


class PermanentError(AnalysisError):
    """Refus définitif : clé invalide, modèle hors du palier souscrit, quota
    épuisé. Réessayer est inutile et retarde le message d'erreur utile."""


class TransientError(AnalysisError):
    """Échec passager (débit limité, panne côté fournisseur).

    À distinguer d'une réponse mal formée : renvoyer immédiatement la même
    requête après un 429 ne fait qu'aggraver la limite, et lui accoler « ta
    réponse n'était pas du JSON valide » n'a aucun sens puisque le modèle n'a
    jamais répondu.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


MAX_ATTEMPTS = 4
BACKOFF_BASE_S = 2.0
BACKOFF_MAX_S = 30.0


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(content: str) -> dict:
    """Certains modèles ouverts enrobent le JSON malgré la consigne."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.DOTALL)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(content)
        if not match:
            raise AnalysisError("Réponse du modèle sans JSON exploitable")
        return json.loads(match.group(0))


def _coerce(payload: dict, model_name: str) -> LlmAnalysis:
    raw_axes = payload.get("axes") or {}
    axes: dict[str, AxisScore] = {}

    for name in AXES:
        entry = raw_axes.get(name)
        if not isinstance(entry, dict):
            raise AnalysisError(f"Axe manquant dans la réponse : {name}")
        try:
            score = int(round(float(entry.get("score"))))
        except (TypeError, ValueError):
            raise AnalysisError(f"Score illisible pour l'axe {name}")
        axes[name] = AxisScore(
            score=max(0, min(100, score)),
            justification=str(entry.get("justification", "")).strip(),
        )

    return LlmAnalysis(
        axes=axes,
        point_fort=str(payload.get("point_fort", "")).strip(),
        axe_prioritaire=str(payload.get("axe_prioritaire", "")).strip(),
        exercice=str(payload.get("exercice", "")).strip(),
        reformulation=str(payload.get("reformulation", "")).strip(),
        model=model_name,
        rubric_version=RUBRIC_VERSION,
    )


class OpenAICompatibleAnalyst:
    """Client chat completions compatible OpenAI : Mistral, Together,
    OpenRouter, Groq, vLLM auto-hébergé..."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _call(self, messages: list[dict[str, str]]) -> str:
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.llm_model,
                "messages": messages,
                "temperature": self.settings.llm_temperature,
                "response_format": {"type": "json_object"},
                "max_tokens": 1500,
            },
            timeout=self.settings.timeout_s,
        )
        if response.status_code == 429 or response.status_code >= 500:
            retry_after = response.headers.get("Retry-After")
            raise TransientError(
                f"Fournisseur indisponible ({response.status_code}) : "
                f"{response.text[:200]}",
                retry_after=float(retry_after) if retry_after and retry_after.isdigit() else None,
            )
        if response.status_code >= 400:
            raise PermanentError(
                f"Analyse refusée ({response.status_code}) : {response.text[:300]}"
            )
        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise AnalysisError(f"Réponse inattendue du fournisseur : {exc}") from exc

    def analyse(
        self, domain: str, topic: str, time_limit_s: int,
        metrics: SpeechMetrics, transcript_text: str,
    ) -> LlmAnalysis:
        if not self.settings.llm_api_key:
            raise AnalysisError("ELOQ_LLM_API_KEY manquante")

        messages = build_messages(domain, topic, time_limit_s, metrics, transcript_text)

        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                content = self._call(messages)
                return _coerce(_extract_json(content), self.settings.llm_model)

            except PermanentError:
                raise  # inutile d'insister : l'erreur ne changera pas

            except TransientError as exc:
                last_error = exc
                if attempt == MAX_ATTEMPTS - 1:
                    break
                # Attente exponentielle, avec un décalage aléatoire pour ne pas
                # synchroniser plusieurs utilisateurs sur la même reprise.
                delay = exc.retry_after or min(
                    BACKOFF_BASE_S * (2 ** attempt), BACKOFF_MAX_S
                )
                time.sleep(delay + random.uniform(0, 0.5))

            except (AnalysisError, ValidationError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == MAX_ATTEMPTS - 1:
                    break
                # Réponse reçue mais inexploitable : on rappelle la contrainte
                # de format, une seule fois, et on repart du prompt d'origine
                # pour ne pas empiler les rappels.
                messages = build_messages(
                    domain, topic, time_limit_s, metrics, transcript_text
                ) + [{
                    "role": "user",
                    "content": "Ta réponse n'était pas un JSON valide conforme au modèle "
                               "demandé. Renvoie uniquement l'objet JSON, sans aucun texte "
                               "autour.",
                }]

        raise AnalysisError(
            f"Analyse impossible après {MAX_ATTEMPTS} tentatives : {last_error}"
        )


class MockAnalyst:
    """Analyse simulée, dérivée des métriques réelles.

    Permet de faire tourner et de tester le pipeline de bout en bout sans clé
    d'API. Les scores sont grossiers et ne valent rien pédagogiquement : c'est
    un substitut d'intégration, pas un juge.
    """

    def analyse(
        self, domain: str, topic: str, time_limit_s: int,
        metrics: SpeechMetrics, transcript_text: str,
    ) -> LlmAnalysis:
        base = 45
        if metrics.word_count > 180:
            base += 10
        if metrics.mattr > 0.70:
            base += 8
        if metrics.duration_s >= time_limit_s * 0.8:
            base += 7

        axes = {
            name: AxisScore(
                score=max(0, min(100, base + offset)),
                justification=f"[simulation] Axe « {AXES[name]['label']} » non évalué : "
                              "aucun modèle configuré.",
            )
            for name, offset in zip(AXES, (0, 5, -5, 3, -3))
        }

        return LlmAnalysis(
            axes=axes,
            point_fort="[simulation] Configurez ELOQ_LLM_API_KEY pour une analyse réelle.",
            axe_prioritaire=metrics.fluency_notes[1] if len(metrics.fluency_notes) > 1
                            else "[simulation] Analyse indisponible.",
            exercice="[simulation] Renseignez un fournisseur LLM pour obtenir un exercice.",
            reformulation="",
            model="mock",
            rubric_version=RUBRIC_VERSION,
        )


def build_analyst(settings: Settings):
    if settings.llm_provider == "mock":
        return MockAnalyst()
    return OpenAICompatibleAnalyst(settings)
