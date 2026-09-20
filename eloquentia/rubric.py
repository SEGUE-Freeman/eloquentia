"""Grille de notation figée et construction du prompt.

Pourquoi une grille écrite plutôt qu'un « note son éloquence sur 100 » : sans
ancrages explicites, un LLM note à l'intuition, et la même prestation reçoit
62 puis 78 selon la formulation du jour. Les descripteurs ci-dessous fixent ce
que vaut chaque palier ; c'est ce qui rend deux sessions comparables.

Toute modification de cette grille change l'échelle : RUBRIC_VERSION doit être
incrémentée, et les scores d'une version ne doivent jamais être tracés sur la
même courbe que ceux d'une autre.
"""

from __future__ import annotations

import json

from .models import SpeechMetrics

RUBRIC_VERSION = "1.0"

# Poids du score global. L'aisance vient du code (metrics.fluency_score), les
# cinq autres du LLM.
GLOBAL_WEIGHTS = {
    "aisance": 0.25,
    "structure": 0.20,
    "contenu": 0.20,
    "pertinence": 0.15,
    "langue": 0.10,
    "impact": 0.10,
}

AXES: dict[str, dict[str, str]] = {
    "structure": {
        "label": "Structure",
        "question": "Le discours a-t-il une architecture audible : ouverture, progression, chute ?",
        "anchors": (
            "0-20 : suite d'idées sans ordre, on ne sait ni où ça commence ni où ça va. "
            "21-40 : un début identifiable, puis une énumération qui s'arrête faute de temps. "
            "41-60 : un fil conducteur existe mais les transitions sont absentes ou artificielles. "
            "61-80 : ouverture nette, deux ou trois mouvements distincts, conclusion qui referme le propos. "
            "81-100 : architecture évidente à l'oreille, transitions qui font avancer, chute qui répond à l'ouverture."
        ),
    },
    "pertinence": {
        "question": "Le sujet imposé est-il réellement traité, ou sert-il de prétexte ?",
        "label": "Pertinence",
        "anchors": (
            "0-20 : le sujet est cité puis abandonné, le discours parle d'autre chose. "
            "21-40 : lien lâche, le propos tiendrait tel quel sur un autre sujet. "
            "41-60 : le sujet est traité mais de façon générale, sans angle propre. "
            "61-80 : angle choisi et assumé, le sujet est pris par un côté précis. "
            "81-100 : le sujet est problématisé, reformulé, et le discours répond à la question qu'il a posée."
        ),
    },
    "contenu": {
        "label": "Contenu et culture",
        "question": "Y a-t-il de la matière : exemples concrets, références justes, idées non banales ?",
        "anchors": (
            "0-20 : généralités interchangeables, aucun exemple. "
            "21-40 : une idée répétée sous trois formes, exemples vagues. "
            "41-60 : idées correctes et exemples présents mais attendus. "
            "61-80 : exemples précis et vérifiables, au moins une référence pertinente, une idée qui surprend. "
            "81-100 : matière dense et exacte, références convoquées à bon escient, point de vue original et soutenu."
        ),
    },
    "langue": {
        "label": "Langue",
        "question": "Syntaxe, précision du vocabulaire, registre, images.",
        "anchors": (
            "0-20 : phrases inachevées, vocabulaire approximatif, sens souvent flou. "
            "21-40 : syntaxe relâchée, mots passe-partout (chose, truc, faire). "
            "41-60 : langue correcte mais plate, peu de variation de construction. "
            "61-80 : vocabulaire précis, phrases construites, quelques images qui fonctionnent. "
            "81-100 : langue tenue et vivante, rythme des phrases travaillé, formules qui se retiennent."
        ),
    },
    "impact": {
        "label": "Impact",
        "question": "Le discours convainc-t-il, s'adresse-t-il à quelqu'un, laisse-t-il une trace ?",
        "anchors": (
            "0-20 : récitation sans destinataire, rien ne reste. "
            "21-40 : intention perceptible mais aucune adresse à l'auditoire. "
            "41-60 : on suit sans être engagé. "
            "61-80 : adresse claire, montée en intensité, une formule qui reste. "
            "81-100 : on est tenu du début à la fin, la chute est mémorable."
        ),
    },
}

SYSTEM_PROMPT = f"""Tu es jury d'un concours d'éloquence francophone, spécialisé dans l'exercice du discours improvisé sur sujet imposé. Tu es exigeant et concret : ton retour doit être utilisable dès la prestation suivante.

GRILLE DE NOTATION (version {RUBRIC_VERSION}) — applique-la à la lettre, palier par palier :
{chr(10).join(f"- {name} ({a['label']}) : {a['question']} {a['anchors']}" for name, a in AXES.items())}

RÈGLES IMPÉRATIVES
1. Tu notes uniquement les cinq axes ci-dessus. Le débit, les pauses, les tics de langage et l'intonation ont DÉJÀ été mesurés par des outils acoustiques : ces chiffres te sont fournis comme des faits. Tu peux t'y référer, jamais les contredire ni les re-noter.
2. Le texte provient d'une transcription automatique. Ignore la ponctuation, l'orthographe et les mots manifestement mal transcrits : juge le discours, pas la transcription.
3. Chaque justification cite un élément précis du discours (une formule, un exemple, un enchaînement). Pas de commentaire qui pourrait s'appliquer à n'importe quelle prestation.
4. Si une référence culturelle ou un fait avancé est faux, signale-le explicitement dans la justification de « contenu » et baisse la note en conséquence.
5. Un seul point fort et un seul axe prioritaire. Un orateur qui reçoit dix reproches n'en corrige aucun.
6. L'exercice proposé est une consigne concrète et réalisable lors de la prochaine prise de parole, pas un conseil général.
7. Écris en français, tutoiement, ton direct. N'accorde jamais d'adjectif au genre de la personne : commente le discours, pas l'orateur.
8. Réponds exclusivement par un objet JSON valide, sans texte autour, sans bloc de code."""

OUTPUT_TEMPLATE = {
    "axes": {
        name: {"score": "<entier 0-100>", "justification": "<1 à 2 phrases citant le discours>"}
        for name in AXES
    },
    "point_fort": "<le seul point fort à retenir, 1 phrase>",
    "axe_prioritaire": "<le seul défaut à corriger en priorité, 1 phrase>",
    "exercice": "<consigne concrète pour la prochaine prise de parole, 1 phrase>",
    "reformulation": "<une phrase faible du discours, réécrite telle qu'elle aurait dû être dite>",
}


def format_measured_facts(metrics: SpeechMetrics, time_limit_s: int) -> str:
    """Les mesures transmises au LLM comme faits établis, pas comme opinions."""

    lines = [
        f"- Durée du discours : {metrics.duration_s:.0f} s sur {time_limit_s} s imparties",
        f"- Nombre de mots : {metrics.word_count}",
        f"- Débit en articulation : {metrics.articulation_wpm:.0f} mots/min "
        f"(zone confortable : 140-175)",
        f"- Silences longs (> 1,5 s) : {metrics.pauses.count_long} "
        f"(le plus long : {metrics.pauses.longest_s:.1f} s à {metrics.pauses.longest_at:.0f} s)",
        f"- Part de silence : {metrics.pauses.silence_ratio:.0%} du temps total",
        f"- Tics de langage : {metrics.filler_count} au total "
        f"({metrics.filler_per_min:.1f} par minute)",
        f"- Richesse lexicale (MATTR) : {metrics.mattr:.2f}",
        f"- Score d'aisance calculé : {metrics.fluency_score}/100",
    ]

    if metrics.fillers:
        detail = ", ".join(f"« {f.pattern} » x{f.count}" for f in metrics.fillers[:6])
        lines.append(f"- Détail des tics : {detail}")
    if metrics.overused_words:
        detail = ", ".join(f"« {w} » x{c}" for w, c in metrics.overused_words)
        lines.append(f"- Mots sur-utilisés : {detail}")
    if metrics.prosody is not None:
        lines.append(
            f"- Intonation : variation de {metrics.prosody.pitch_variation_st:.1f} demi-tons "
            f"({'voix plate' if metrics.prosody.monotony_flag else 'intonation vivante'})"
        )
    else:
        lines.append("- Intonation : non mesurée sur cet enregistrement")

    return "\n".join(lines)


def build_messages(
    domain: str,
    topic: str,
    time_limit_s: int,
    metrics: SpeechMetrics,
    transcript_text: str,
) -> list[dict[str, str]]:
    user_prompt = f"""DOMAINE : {domain}
SUJET IMPOSÉ : {topic}
TEMPS IMPARTI : {time_limit_s} secondes

MESURES ACOUSTIQUES (faits établis, ne pas re-noter) :
{format_measured_facts(metrics, time_limit_s)}

TRANSCRIPTION DU DISCOURS :
\"\"\"
{transcript_text}
\"\"\"

Renvoie exactement cette structure JSON, en remplaçant chaque valeur :
{json.dumps(OUTPUT_TEMPLATE, ensure_ascii=False, indent=2)}"""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def compute_global_score(fluency_score: int, axis_scores: dict[str, int]) -> int:
    """Score global pondéré. Les poids sont figés avec la grille : les changer
    casse la comparabilité historique."""
    total = fluency_score * GLOBAL_WEIGHTS["aisance"]
    weight_used = GLOBAL_WEIGHTS["aisance"]
    for name, score in axis_scores.items():
        weight = GLOBAL_WEIGHTS.get(name)
        if weight:
            total += score * weight
            weight_used += weight
    return int(round(total / weight_used)) if weight_used else 0
