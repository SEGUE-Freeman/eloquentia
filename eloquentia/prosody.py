"""Analyse du signal audio : ce que la transcription ne peut pas dire.

Un texte ne révèle pas une voix monocorde. Or « parler dans le micro sans
jamais varier la hauteur » est l'un des défauts les plus coûteux à l'oral, et
l'un des plus invisibles pour celui qui parle. On le mesure donc directement
sur le signal.

Ce module est optionnel : si l'audio n'est pas décodable, le pipeline continue
sans prosodie plutôt que d'échouer.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .models import ProsodyStats

# Bornes de la voix humaine parlée, tous registres confondus.
F0_MIN_HZ = 70.0
F0_MAX_HZ = 350.0

FRAME_S = 0.040
HOP_S = 0.020

# En dessous de ce seuil, l'intonation est objectivement plate.
MONOTONY_THRESHOLD_ST = 2.0


class AudioDecodeError(RuntimeError):
    pass


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    if sample_width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif sample_width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise AudioDecodeError(f"Largeur d'échantillon non gérée : {sample_width}")

    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)
    return data, rate


def _decode_with_ffmpeg(path: Path) -> tuple[np.ndarray, int]:
    """Le navigateur enregistre en webm/opus : ffmpeg est la voie de conversion.

    Absent du serveur, la prosodie est simplement désactivée.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise AudioDecodeError("ffmpeg introuvable : prosodie désactivée")

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "audio.wav"
        proc = subprocess.run(
            [ffmpeg, "-nostdin", "-y", "-i", str(path),
             "-ac", "1", "-ar", "16000", "-f", "wav", str(out)],
            capture_output=True,
        )
        if proc.returncode != 0 or not out.exists():
            raise AudioDecodeError("ffmpeg n'a pas pu décoder l'audio")
        return _read_wav(out)


def load_audio(path: str | Path) -> tuple[np.ndarray, int]:
    path = Path(path)
    if path.suffix.lower() == ".wav":
        try:
            return _read_wav(path)
        except (wave.Error, EOFError):
            pass  # WAV illisible : on retente via ffmpeg
    return _decode_with_ffmpeg(path)


def _autocorrelation_f0(frame: np.ndarray, rate: int) -> float:
    """Fréquence fondamentale d'une trame par autocorrélation.

    Méthode volontairement simple : on cherche une tendance d'intonation sur
    des centaines de trames, pas une transcription musicale. Les erreurs
    isolées sont absorbées par la médiane et l'écart-type.
    """
    frame = frame - frame.mean()
    if np.all(frame == 0):
        return 0.0

    corr = np.correlate(frame, frame, mode="full")[len(frame) - 1:]
    if corr[0] <= 0:
        return 0.0

    min_lag = int(rate / F0_MAX_HZ)
    max_lag = int(rate / F0_MIN_HZ)
    if max_lag >= len(corr) or min_lag >= max_lag:
        return 0.0

    window = corr[min_lag:max_lag]
    peak = int(np.argmax(window)) + min_lag

    # Un pic trop faible signifie une trame non voisée (consonne, souffle).
    if corr[peak] / corr[0] < 0.30:
        return 0.0
    return rate / peak


def analyse_prosody(path: str | Path) -> ProsodyStats | None:
    """Retourne les mesures d'intonation, ou None si l'audio est inexploitable."""

    try:
        signal, rate = load_audio(path)
    except (AudioDecodeError, FileNotFoundError, OSError):
        return None

    if signal.size < rate:  # moins d'une seconde : rien à mesurer
        return None

    frame_len = int(FRAME_S * rate)
    hop = int(HOP_S * rate)
    n_frames = 1 + (len(signal) - frame_len) // hop
    if n_frames < 10:
        return None

    frames = np.lib.stride_tricks.as_strided(
        signal,
        shape=(n_frames, frame_len),
        strides=(signal.strides[0] * hop, signal.strides[0]),
    )

    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    if rms.max() <= 0:
        return None

    # Seuil de voisement relatif : robuste au niveau d'enregistrement, qui
    # varie d'un micro et d'un utilisateur à l'autre.
    threshold = max(rms.max() * 0.10, np.percentile(rms, 40))
    voiced = rms >= threshold
    voiced_ratio = float(voiced.mean())
    if voiced.sum() < 10:
        return None

    f0s = np.array([
        _autocorrelation_f0(frames[i], rate)
        for i in np.flatnonzero(voiced)
    ])
    f0s = f0s[(f0s >= F0_MIN_HZ) & (f0s <= F0_MAX_HZ)]
    if f0s.size < 10:
        return None

    median_f0 = float(np.median(f0s))
    # Variation exprimée en demi-tons : comparable d'une voix grave à une voix
    # aiguë, contrairement à un écart-type en hertz.
    semitones = 12.0 * np.log2(f0s / median_f0)
    # On écarte les 5 % extrêmes, qui sont surtout des erreurs d'octave.
    trimmed = semitones[
        (semitones >= np.percentile(semitones, 5))
        & (semitones <= np.percentile(semitones, 95))
    ]
    pitch_variation = float(np.std(trimmed if trimmed.size >= 10 else semitones))

    voiced_rms = rms[voiced]
    energy_variation = float(voiced_rms.std() / voiced_rms.mean()) if voiced_rms.mean() > 0 else 0.0

    return ProsodyStats(
        median_f0_hz=round(median_f0, 1),
        pitch_variation_st=round(pitch_variation, 2),
        energy_variation=round(energy_variation, 3),
        voiced_ratio=round(voiced_ratio, 3),
        monotony_flag=pitch_variation < MONOTONY_THRESHOLD_ST,
    )
