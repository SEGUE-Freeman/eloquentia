"""Configuration par variables d'environnement.

Les deux fournisseurs (transcription et LLM) sont interchangeables tant qu'ils
exposent une API compatible OpenAI, ce qui est le cas de la quasi-totalité des
hébergeurs de modèles open source. Changer de fournisseur = changer deux
variables, sans toucher au code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Charge un .env sans dépendance externe. Les variables déjà définies
    dans l'environnement restent prioritaires."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    # --- Transcription ---
    stt_provider: str = "mock"          # "openai_compatible" | "mock"
    stt_base_url: str = "https://api.groq.com/openai/v1"
    stt_api_key: str = ""
    stt_model: str = "whisper-large-v3"

    # --- Analyse ---
    llm_provider: str = "mock"          # "openai_compatible" | "mock"
    llm_base_url: str = "https://api.mistral.ai/v1"
    llm_api_key: str = ""
    llm_model: str = "mistral-large-latest"

    # Température 0 : deux analyses de la même prestation doivent donner la
    # même note, sinon le suivi de progression est du bruit.
    llm_temperature: float = 0.0
    timeout_s: int = 120

    data_dir: Path = Path("data")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            stt_provider=os.getenv("ELOQ_STT_PROVIDER", "mock"),
            stt_base_url=os.getenv("ELOQ_STT_BASE_URL", cls.stt_base_url),
            stt_api_key=os.getenv("ELOQ_STT_API_KEY", ""),
            stt_model=os.getenv("ELOQ_STT_MODEL", cls.stt_model),
            llm_provider=os.getenv("ELOQ_LLM_PROVIDER", "mock"),
            llm_base_url=os.getenv("ELOQ_LLM_BASE_URL", cls.llm_base_url),
            llm_api_key=os.getenv("ELOQ_LLM_API_KEY", ""),
            llm_model=os.getenv("ELOQ_LLM_MODEL", cls.llm_model),
            llm_temperature=float(os.getenv("ELOQ_LLM_TEMPERATURE", "0")),
            timeout_s=int(os.getenv("ELOQ_TIMEOUT_S", "120")),
            data_dir=Path(os.getenv("ELOQ_DATA_DIR", "data")),
        )
