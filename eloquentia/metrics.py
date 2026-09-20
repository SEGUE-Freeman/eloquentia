"""Métriques calculées par le code, jamais par un LLM.

Règle du projet : tout ce qui est mesurable est mesuré ici. Un LLM à qui on
demande « quel était son débit ? » invente un chiffre plausible ; le même calcul
lancé deux fois ici donne deux fois le même résultat. C'est la condition pour
qu'une courbe de progression veuille dire quelque chose.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .models import FillerHit, PauseStats, ProsodyStats, SpeechMetrics, Word

# --------------------------------------------------------------------------
# Tokenisation française
# --------------------------------------------------------------------------

_LETTERS = r"a-zA-Zà-öø-ÿÀ-ÖØ-Þœæ"
# Garde les apostrophes internes (j'ai, aujourd'hui) et les traits d'union
# (peut-être, c'est-à-dire), qui portent du sens en français.
_TOKEN_RE = re.compile(rf"[{_LETTERS}]+(?:['’-][{_LETTERS}]+)*")
_SENTENCE_RE = re.compile(r"[.!?…]+")


def strip_accents(s: str) -> str:
    """Clé de comparaison robuste : « voilà » et « voila » sont le même tic."""
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def normalize(s: str) -> str:
    return strip_accents(s.lower().replace("’", "'"))


def tokenize(text: str) -> list[str]:
    return [normalize(m.group(0)) for m in _TOKEN_RE.finditer(text)]


# --------------------------------------------------------------------------
# Tics de langage
# --------------------------------------------------------------------------

# Hésitations pures : toujours un tic, quel qu'en soit le nombre.
HARD_FILLERS = {
    "euh", "heu", "hein", "hum", "heum", "mmh", "bah", "ben", "bein", "beh",
}

# Béquilles de discours : normales en petite quantité, tics au-delà. Elles sont
# comptées, et la pénalité s'applique via le taux global par minute.
SOFT_FILLERS = [
    "du coup", "en fait", "voila", "genre", "tu vois", "vous voyez",
    "je veux dire", "j'veux dire", "on va dire", "disons", "c'est a dire",
    "quelque part", "si vous voulez", "en gros", "effectivement",
    "tout a fait", "au final", "de toute facon",
]

# Mots-outils exclus du calcul de sur-utilisation.
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "au", "aux", "et", "ou",
    "mais", "donc", "or", "ni", "car", "que", "qui", "quoi", "dont", "ce",
    "cet", "cette", "ces", "je", "tu", "il", "elle", "on", "nous", "vous",
    "ils", "elles", "me", "te", "se", "lui", "leur", "y", "en", "a", "dans",
    "sur", "sous", "pour", "par", "avec", "sans", "vers", "chez", "est",
    "sont", "etre", "avoir", "ai", "as", "ont", "avons", "avez", "fait",
    "faire", "plus", "moins", "tres", "bien", "tout", "tous", "toute",
    "toutes", "meme", "aussi", "alors", "comme", "si", "ne", "pas",
    "c'est", "j'ai", "cela", "ca", "son", "sa", "ses", "mon", "ma",
    "mes", "notre", "nos", "votre", "vos", "leurs", "d'un", "d'une",
    "cette", "etait", "sera", "peut", "veut", "doit", "quand", "ils",
}


def _filler_spans(text: str) -> list[tuple[int, int]]:
    """Positions des tics dans le texte brut, expressions multi-mots comprises."""
    matches = list(_TOKEN_RE.finditer(text))
    tokens = [normalize(m.group(0)) for m in matches]

    spans: list[tuple[int, int]] = []
    consumed: set[int] = set()

    for expr in SOFT_FILLERS:
        parts = expr.split()
        n = len(parts)
        if n < 2:
            continue
        for i in range(len(tokens) - n + 1):
            if any(j in consumed for j in range(i, i + n)):
                continue
            if tokens[i:i + n] == parts:
                spans.append((matches[i].start(), matches[i + n - 1].end()))
                consumed.update(range(i, i + n))

    single_soft = {e for e in SOFT_FILLERS if " " not in e}
    for i, tok in enumerate(tokens):
        if i in consumed:
            continue
        if tok in HARD_FILLERS or tok in single_soft:
            spans.append((matches[i].start(), matches[i].end()))

    return sorted(spans)


# Nettoyage de la ponctuation orpheline laissée par une suppression.
_CLEAN_RULES = (
    (re.compile(r"\s+([,;:.!?])"), r"\1"),      # espace avant ponctuation
    (re.compile(r"([,;:])\s*(?=[,;:.!?])"), ""),  # ponctuations accolées
    (re.compile(r"([.!?])\s*,"), r"\1"),          # « . , » -> « . »
    (re.compile(r"^\s*[,;:]\s*", re.MULTILINE), ""),  # phrase ouvrant sur une virgule
    (re.compile(r"[ \t]{2,}"), " "),
    (re.compile(r"\s+\n"), "\n"),
)


def strip_fillers(text: str) -> str:
    """Retire les tics du texte, pour la version transmise au LLM.

    Les tics sont déjà comptés et sanctionnés par le score d'aisance. Tant
    qu'ils restent visibles dans la transcription, le modèle les commente et
    baisse ses notes à cause d'eux — on l'a vérifié : ni une consigne explicite
    ni le retrait des mesures du prompt n'y suffisent. Le texte nettoyé supprime
    la tentation à la source, et recentre le jugement sur ce qui a été dit
    plutôt que sur la manière dont ça a hésité.

    La transcription brute reste évidemment intacte : c'est elle qui alimente
    les mesures et que l'orateur relit.
    """
    spans = _filler_spans(text)
    if not spans:
        return text

    out: list[str] = []
    prev = 0
    for start, end in spans:
        out.append(text[prev:start])
        prev = end
    out.append(text[prev:])

    cleaned = "".join(out)
    for pattern, replacement in _CLEAN_RULES:
        cleaned = pattern.sub(replacement, cleaned)

    # Une phrase peut commencer en minuscule après suppression d'un tic initial.
    cleaned = re.sub(
        r"(^|[.!?]\s+)([a-zà-öø-ÿ])",
        lambda m: m.group(1) + m.group(2).upper(),
        cleaned,
    )
    return cleaned.strip()


def detect_fillers(words: list[Word], text: str) -> tuple[list[FillerHit], int]:
    """Détecte les tics sur la séquence de mots horodatés quand elle existe,
    sinon sur le texte brut (sans timestamps d'exemple)."""

    if words:
        tokens = [normalize(w.text.strip(" .,!?;:")) for w in words]
        starts = [w.start for w in words]
    else:
        tokens = tokenize(text)
        starts = [0.0] * len(tokens)

    hits: dict[str, FillerHit] = {}

    def record(pattern: str, at: float) -> None:
        hit = hits.get(pattern)
        if hit is None:
            hit = FillerHit(pattern=pattern, count=0, examples_at=[])
            hits[pattern] = hit
        hit.count += 1
        if len(hit.examples_at) < 5:
            hit.examples_at.append(round(at, 2))

    # Expressions multi-mots d'abord, pour ne pas les recouper.
    consumed: set[int] = set()
    for expr in SOFT_FILLERS:
        parts = expr.split()
        n = len(parts)
        if n < 2:
            continue
        for i in range(len(tokens) - n + 1):
            if any(j in consumed for j in range(i, i + n)):
                continue
            if tokens[i:i + n] == parts:
                record(expr, starts[i])
                consumed.update(range(i, i + n))

    single_soft = {e for e in SOFT_FILLERS if " " not in e}
    for i, tok in enumerate(tokens):
        if i in consumed or not tok:
            continue
        if tok in HARD_FILLERS or tok in single_soft:
            record(tok, starts[i])

    ordered = sorted(hits.values(), key=lambda h: -h.count)
    return ordered, sum(h.count for h in ordered)


# --------------------------------------------------------------------------
# Pauses et débit
# --------------------------------------------------------------------------

MICRO_GAP_S = 0.30    # en deçà : articulation normale, pas une pause
SHORT_PAUSE_S = 0.60  # respiration, structurante quand elle est voulue
LONG_PAUSE_S = 1.50   # trou : hésitation ou perte du fil


def compute_pauses(words: list[Word], duration_s: float) -> tuple[PauseStats, float]:
    """Retourne les stats de pause et le temps de parole effectif."""

    stats = PauseStats()
    if len(words) < 2:
        return stats, duration_s

    silence = 0.0
    for prev, nxt in zip(words, words[1:]):
        gap = nxt.start - prev.end
        if gap < MICRO_GAP_S:
            continue
        silence += gap
        if gap >= LONG_PAUSE_S:
            stats.count_long += 1
        elif gap >= SHORT_PAUSE_S:
            stats.count_short += 1
        if gap > stats.longest_s:
            stats.longest_s = round(gap, 2)
            stats.longest_at = round(prev.end, 2)

    # Blancs de début et de fin : ils comptent dans le silence total mais ne
    # sont pas des pauses de discours.
    lead = max(0.0, words[0].start)
    trail = max(0.0, duration_s - words[-1].end)
    silence += lead + trail

    stats.total_silence_s = round(silence, 2)
    stats.silence_ratio = round(silence / duration_s, 3) if duration_s > 0 else 0.0

    speaking_time = max(0.1, duration_s - silence)
    return stats, speaking_time


# --------------------------------------------------------------------------
# Richesse lexicale
# --------------------------------------------------------------------------

MATTR_WINDOW = 50


def mattr(tokens: list[str], window: int = MATTR_WINDOW) -> float:
    """Type-Token Ratio à fenêtre glissante.

    Le TTR brut chute mécaniquement quand le discours s'allonge : un discours
    d'1 min et un de 3 min ne seraient pas comparables, et la courbe de
    progression afficherait une fausse régression. Le MATTR corrige ce biais.
    """
    if not tokens:
        return 0.0
    if len(tokens) <= window:
        return round(len(set(tokens)) / len(tokens), 3)

    ratios = [
        len(set(tokens[i:i + window])) / window
        for i in range(len(tokens) - window + 1)
    ]
    return round(sum(ratios) / len(ratios), 3)


# --------------------------------------------------------------------------
# Score d'aisance : formule figée
# --------------------------------------------------------------------------

def _piecewise(value: float, points: list[tuple[float, float]]) -> float:
    """Interpolation linéaire entre des ancres (x croissant), bornée aux extrêmes."""
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= value <= x1:
            if x1 == x0:
                return y1
            return y0 + (value - x0) / (x1 - x0) * (y1 - y0)
    return points[-1][1]


# Ancres de débit : en français parlé, la zone confortable pour l'auditeur se
# situe autour de 140-175 mots/min en articulation.
WPM_ANCHORS = [(80, 20.0), (110, 60.0), (140, 100.0), (175, 100.0), (210, 55.0), (250, 15.0)]
FILLER_ANCHORS = [(0, 100.0), (1, 92.0), (2, 80.0), (4, 58.0), (6, 40.0), (10, 12.0), (15, 0.0)]
LONGPAUSE_ANCHORS = [(0, 100.0), (0.5, 90.0), (1.0, 75.0), (2.0, 50.0), (4.0, 20.0), (6.0, 0.0)]
SILENCE_ANCHORS = [(0.10, 85.0), (0.18, 100.0), (0.30, 85.0), (0.40, 55.0), (0.55, 20.0), (0.70, 0.0)]
MATTR_ANCHORS = [(0.45, 10.0), (0.55, 35.0), (0.65, 65.0), (0.75, 90.0), (0.82, 100.0)]
PITCH_ANCHORS = [(0.5, 5.0), (1.5, 35.0), (2.5, 70.0), (3.5, 95.0), (5.0, 100.0), (8.0, 80.0)]

# Occupation du temps imparti. S'arrêter à mi-parcours n'était pas pénalisé
# jusqu'ici : les silences étant mesurés à l'intérieur de ce qui est dit, un
# discours de 30 s sur 120 pouvait décrocher 100. Tenir la durée demandée fait
# pourtant partie de l'exercice — c'est même l'essentiel de sa difficulté.
# Léger malus au-delà de la limite : dépasser, c'est ne pas avoir vu venir sa
# propre conclusion.
TIME_USAGE_ANCHORS = [
    (0.25, 10.0), (0.40, 30.0), (0.55, 55.0), (0.70, 80.0),
    (0.85, 100.0), (1.00, 100.0), (1.15, 75.0), (1.40, 45.0),
]

# Poids du score d'aisance. Les tics pèsent le plus : c'est le défaut le plus
# audible et le plus corrigeable d'un orateur débutant.
FLUENCY_WEIGHTS = {
    "debit": 22.0,
    "tics": 26.0,
    "pauses": 10.0,
    "silence": 7.0,
    "lexique": 13.0,
    "temps": 12.0,
    "intonation": 10.0,
}


def compute_fluency(
    articulation_wpm: float,
    filler_per_min: float,
    long_pause_per_min: float,
    silence_ratio: float,
    mattr_value: float,
    prosody: ProsodyStats | None,
    time_usage_ratio: float = 0.0,
) -> tuple[int, list[str]]:
    """Score d'aisance 0-100, entièrement déterministe.

    Volontairement non confié au LLM : c'est le seul moyen d'affirmer qu'une
    hausse de 8 points entre deux sessions correspond à un vrai progrès et non
    à l'humeur du modèle.
    """

    parts = [
        ("debit", _piecewise(articulation_wpm, WPM_ANCHORS)),
        ("tics", _piecewise(filler_per_min, FILLER_ANCHORS)),
        ("pauses", _piecewise(long_pause_per_min, LONGPAUSE_ANCHORS)),
        ("silence", _piecewise(silence_ratio, SILENCE_ANCHORS)),
        ("lexique", _piecewise(mattr_value, MATTR_ANCHORS)),
    ]
    # Sans temps imparti connu (analyse d'un fichier isolé), la composante est
    # omise et les autres poids se renormalisent.
    if time_usage_ratio > 0:
        parts.append(("temps", _piecewise(time_usage_ratio, TIME_USAGE_ANCHORS)))
    if prosody is not None:
        parts.append(("intonation", _piecewise(prosody.pitch_variation_st, PITCH_ANCHORS)))

    total_weight = sum(FLUENCY_WEIGHTS[name] for name, _ in parts)
    score = sum(value * FLUENCY_WEIGHTS[name] for name, value in parts) / total_weight

    notes: list[str] = []
    if articulation_wpm > 190:
        notes.append(f"Débit de {articulation_wpm:.0f} mots/min : trop rapide, l'auditeur décroche.")
    elif articulation_wpm < 115:
        notes.append(f"Débit de {articulation_wpm:.0f} mots/min : lent, l'attention retombe.")
    else:
        notes.append(f"Débit de {articulation_wpm:.0f} mots/min : bonne zone d'écoute.")

    if filler_per_min >= 4:
        notes.append(f"{filler_per_min:.1f} tics par minute : c'est le premier frein à corriger.")
    elif filler_per_min >= 2:
        notes.append(f"{filler_per_min:.1f} tics par minute : perceptible mais gérable.")
    else:
        notes.append(f"{filler_per_min:.1f} tic par minute : parole propre.")

    if 0 < time_usage_ratio < 0.6:
        notes.append(
            f"{time_usage_ratio:.0%} du temps imparti utilisé : le discours s'arrête "
            "avant d'avoir été développé."
        )
    elif 0.6 <= time_usage_ratio < 0.8:
        notes.append(f"{time_usage_ratio:.0%} du temps imparti : il restait de la place.")
    elif time_usage_ratio > 1.05:
        notes.append("Temps imparti dépassé : la conclusion n'a pas été anticipée.")

    if long_pause_per_min >= 2:
        notes.append("Trop de silences longs : le fil se perd en cours de route.")
    if silence_ratio > 0.40:
        notes.append(f"{silence_ratio:.0%} du temps sans parler : le temps imparti n'est pas exploité.")

    if prosody is not None and prosody.monotony_flag:
        notes.append(
            f"Intonation plate ({prosody.pitch_variation_st:.1f} demi-tons de variation) : "
            "le propos ne décolle pas."
        )

    return int(round(score)), notes


# --------------------------------------------------------------------------
# Entrée principale
# --------------------------------------------------------------------------

def analyse_speech(
    text: str,
    words: list[Word],
    duration_s: float,
    prosody: ProsodyStats | None = None,
    time_limit_s: int = 0,
) -> SpeechMetrics:
    duration_s = max(0.1, duration_s)
    time_usage_ratio = round(duration_s / time_limit_s, 3) if time_limit_s > 0 else 0.0

    pauses, speaking_time = compute_pauses(words, duration_s)
    tokens = tokenize(text)
    word_count = len(words) if words else len(tokens)

    overall_wpm = word_count / (duration_s / 60.0)
    articulation_wpm = word_count / (speaking_time / 60.0)

    fillers, filler_count = detect_fillers(words, text)
    filler_per_min = filler_count / (duration_s / 60.0)
    long_pause_per_min = pauses.count_long / (duration_s / 60.0)

    ttr = round(len(set(tokens)) / len(tokens), 3) if tokens else 0.0
    mattr_value = mattr(tokens)

    immediate_repeats = sum(1 for a, b in zip(tokens, tokens[1:]) if a == b and len(a) > 2)

    content = [t for t in tokens if t not in STOPWORDS and len(t) >= 4]
    overused = [(w, c) for w, c in Counter(content).most_common(8) if c >= 4][:5]

    sentences = [s for s in _SENTENCE_RE.split(text) if s.strip()]
    sentence_count = len(sentences)
    avg_sentence_words = round(len(tokens) / sentence_count, 1) if sentence_count else 0.0

    fluency_score, fluency_notes = compute_fluency(
        articulation_wpm, filler_per_min, long_pause_per_min,
        pauses.silence_ratio, mattr_value, prosody, time_usage_ratio,
    )

    return SpeechMetrics(
        duration_s=round(duration_s, 2),
        speaking_time_s=round(speaking_time, 2),
        word_count=word_count,
        time_limit_s=time_limit_s,
        time_usage_ratio=time_usage_ratio,
        overall_wpm=round(overall_wpm, 1),
        articulation_wpm=round(articulation_wpm, 1),
        pauses=pauses,
        fillers=fillers,
        filler_count=filler_count,
        filler_per_min=round(filler_per_min, 2),
        ttr=ttr,
        mattr=mattr_value,
        immediate_repeats=immediate_repeats,
        overused_words=overused,
        sentence_count=sentence_count,
        avg_sentence_words=avg_sentence_words,
        prosody=prosody,
        fluency_score=fluency_score,
        fluency_notes=fluency_notes,
    )
