"""Serveur web : expose le pipeline d'analyse au navigateur.

Volontairement mince. Toute la logique reste dans le paquet `eloquentia` ; ce
module ne fait que recevoir un fichier audio, appeler le pipeline et renvoyer
le rapport. Un jour où l'on passera en multi-utilisateur avec base de données,
c'est ici qu'on branchera l'authentification — pas dans le moteur.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from eloquentia.analysis import AnalysisError
from eloquentia.config import Settings
from eloquentia.pipeline import analyse_session
from eloquentia.storage import HistoryStore, compute_progress, export_curve
from eloquentia.topics import (
    DOMAINS_BY_KEY,
    UnknownTopic,
    draw,
    resolve,
    resource_payload,
    suggest_resources,
    wheel_payload,
)
from eloquentia.transcription import TranscriptionError

STATIC_DIR = Path(__file__).parent / "static"

# Extensions acceptées. Le navigateur produit du webm/opus ; les autres
# viennent des enregistrements importés depuis le téléphone ou l'ordinateur.
ALLOWED_SUFFIXES = {".webm", ".ogg", ".wav", ".m4a", ".mp3", ".mp4", ".aac", ".flac"}
MAX_UPLOAD_MB = 25

settings = Settings.from_env()
store = HistoryStore(settings.data_dir)
audio_dir = Path(settings.data_dir) / "audio"
audio_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Eloquentia", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def accueil() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/domains")
def domains() -> list[dict]:
    """Secteurs de la roue."""
    return wheel_payload()


@app.post("/api/draw")
def tirage(user: str = Form("anonyme"), level: str = Form("")) -> dict:
    """Tire un domaine puis un sujet, en évitant ce qui vient d'être travaillé.

    Le tirage est fait ici et non dans le navigateur : c'est la seule façon de
    tenir compte de l'historique, et d'empêcher que le sujet annoncé diverge de
    celui qui sera enregistré avec la session.
    """
    history = store.load(user)
    domain, topic = draw(
        recent_domains=[r.domain for r in history[-3:]],
        recent_topics=[r.topic for r in history[-15:]],
        level=level or None,
    )
    return {
        "domain_key": domain.key,
        "topic_index": domain.topics.index(topic),
        "domain": domain.label,
        "level": domain.level,
        "color": domain.color,
        "topic": topic,
    }


@app.post("/api/sessions")
async def creer_session(
    audio: UploadFile,
    domain_key: str = Form(...),
    topic_index: int = Form(...),
    time_limit_s: int = Form(120),
    user: str = Form("anonyme"),
) -> JSONResponse:
    """Reçoit l'enregistrement, lance l'analyse, renvoie le rapport.

    Le sujet est résolu ici à partir de son identifiant, jamais repris du texte
    envoyé par le client : c'est la seule façon de garantir que le discours est
    jugé sur la question réellement tirée, dans son orthographe exacte.
    """

    try:
        domaine, sujet = resolve(domain_key, topic_index)
    except UnknownTopic as exc:
        raise HTTPException(400, str(exc)) from exc

    suffix = Path(audio.filename or "").suffix.lower() or ".webm"
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"Format audio non géré : {suffix}")

    session_id = uuid.uuid4().hex[:12]
    destination = audio_dir / f"{session_id}{suffix}"

    with destination.open("wb") as fh:
        shutil.copyfileobj(audio.file, fh)

    taille_mo = destination.stat().st_size / (1024 * 1024)
    if taille_mo > MAX_UPLOAD_MB:
        destination.unlink(missing_ok=True)
        raise HTTPException(413, f"Enregistrement trop lourd ({taille_mo:.0f} Mo)")
    if taille_mo < 0.002:
        destination.unlink(missing_ok=True)
        raise HTTPException(400, "Enregistrement vide : le micro n'a rien capté.")

    try:
        report = analyse_session(
            audio_path=destination,
            domain=domaine.label,
            topic=sujet,
            time_limit_s=time_limit_s,
            user_id=user,
            settings=settings,
        )
    except TranscriptionError as exc:
        raise HTTPException(502, f"Transcription impossible : {exc}") from exc
    except AnalysisError as exc:
        raise HTTPException(502, f"Analyse impossible : {exc}") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    report.audio_path = destination.name
    store.save(report)

    # Les ressources ne sont pas stockées dans le rapport : elles sont dérivées
    # du sujet, et la liste évoluera. Les figer dans l'historique reviendrait à
    # conserver des suggestions périmées.
    return JSONResponse({
        **report.model_dump(mode="json"),
        "resources": [
            resource_payload(r) for r in suggest_resources(domaine, sujet, limit=3)
        ],
    })


@app.get("/api/audio/{nom}")
def audio_session(nom: str) -> FileResponse:
    """Réécoute d'un enregistrement — indispensable pour aller entendre la
    pause de 3 secondes que les mesures signalent."""
    chemin = (audio_dir / nom).resolve()
    if audio_dir.resolve() not in chemin.parents or not chemin.exists():
        raise HTTPException(404, "Enregistrement introuvable")
    return FileResponse(chemin)


@app.get("/api/history/{user}")
def historique(user: str) -> dict:
    history = store.load(user)
    return {
        "courbe": export_curve(history),
        "progression": compute_progress(history),
        "domaines_travailles": sorted({r.domain for r in history}),
        "total": len(history),
    }


@app.get("/api/health")
def sante() -> dict:
    """État de la configuration, pour diagnostiquer sans lire les logs."""
    return {
        "transcription": bool(settings.stt_api_key) or settings.stt_provider == "mock",
        "analyse": bool(settings.llm_api_key) or settings.llm_provider == "mock",
        "modele": settings.llm_model,
        "domaines": len(DOMAINS_BY_KEY),
    }
