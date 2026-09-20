"""Validation du détecteur d'intonation sur des signaux de référence.

On ne peut pas vérifier « cette voix est monocorde » sur un enregistrement réel
sans juge humain. On vérifie donc l'inverse : sur un signal dont la hauteur est
connue par construction, le module doit retrouver cette hauteur et distinguer
une intonation plate d'une intonation variée.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from eloquentia.prosody import analyse_prosody

RATE = 16000


def _write_wav(path: Path, samples: np.ndarray) -> None:
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(pcm.tobytes())


def _voice_like(f0_series: np.ndarray) -> np.ndarray:
    """Signal harmonique à fréquence fondamentale variable, grossièrement
    comparable à une voyelle tenue (fondamentale + deux harmoniques)."""
    phase = np.cumsum(2 * np.pi * f0_series / RATE)
    return (
        0.6 * np.sin(phase)
        + 0.3 * np.sin(2 * phase)
        + 0.1 * np.sin(3 * phase)
    )


def test_detecte_la_hauteur_reelle(tmp_path):
    n = RATE * 3
    signal = _voice_like(np.full(n, 130.0))
    path = tmp_path / "flat.wav"
    _write_wav(path, signal)

    stats = analyse_prosody(path)
    assert stats is not None
    # 3 % de tolérance : la résolution dépend du pas d'autocorrélation.
    assert abs(stats.median_f0_hz - 130.0) / 130.0 < 0.03


def test_voix_plate_signalee(tmp_path):
    n = RATE * 3
    signal = _voice_like(np.full(n, 120.0))
    path = tmp_path / "mono.wav"
    _write_wav(path, signal)

    stats = analyse_prosody(path)
    assert stats is not None
    assert stats.pitch_variation_st < 1.0
    assert stats.monotony_flag is True


def test_intonation_variee_non_signalee(tmp_path):
    n = RATE * 3
    t = np.arange(n) / RATE
    # Hauteur oscillant d'environ +/- 5 demi-tons autour de 150 Hz.
    f0 = 150.0 * (2 ** (5.0 * np.sin(2 * np.pi * 0.5 * t) / 12))
    path = tmp_path / "varie.wav"
    _write_wav(path, _voice_like(f0))

    stats = analyse_prosody(path)
    assert stats is not None
    assert stats.pitch_variation_st > 2.0
    assert stats.monotony_flag is False


def test_audio_illisible_ne_casse_pas(tmp_path):
    path = tmp_path / "corrompu.wav"
    path.write_bytes(b"ceci n'est pas un wav")
    assert analyse_prosody(path) is None


def test_fichier_absent_ne_casse_pas(tmp_path):
    assert analyse_prosody(tmp_path / "inexistant.wav") is None
