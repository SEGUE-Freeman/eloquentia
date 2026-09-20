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

# 1.1 : interdit au modèle de fonder ses notes sur les mesures acoustiques.
# En 1.0, il pénalisait les tics dans l'axe « langue » alors que le score
# d'aisance les sanctionnait déjà, et proposait comme axe prioritaire ce que
# les mesures disaient déjà. Le même défaut comptait deux fois.
#
# 1.2 : ancrage explicite du niveau de référence. En 1.1, les paliers étaient
# calibrés sur une finale de concours : un discours honnête de débutant tombait
# vers 25-30, ce qui informe mal et décourage. Le point médian est désormais
# défini — 50 = prestation correcte pour une improvisation de deux minutes.
RUBRIC_VERSION = "1.2"

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
            "0-20 : aucune organisation perceptible, on ne sait ni où ça commence ni où ça va. "
            "21-40 : des idées juxtaposées, sans début ni fin marqués. "
            "41-60 : un début et une fin identifiables, un fil qu'on arrive à suivre, mais des transitions absentes. "
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
            "21-40 : une seule idée répétée sous trois formes, exemples vagues. "
            "41-60 : des exemples réels, même personnels ou attendus, et des idées correctes. "
            "61-80 : exemples précis et vérifiables, au moins une référence pertinente, une idée qui surprend. "
            "81-100 : matière dense et exacte, références convoquées à bon escient, point de vue original et soutenu."
        ),
    },
    "langue": {
        "label": "Langue",
        "question": "Syntaxe, précision du vocabulaire, registre, images.",
        "anchors": (
            "0-20 : le sens se perd, phrases abandonnées en cours de route, vocabulaire hors sujet. "
            "21-40 : syntaxe très relâchée, mots passe-partout (chose, truc, faire) à chaque phrase. "
            "41-60 : langue correcte mais plate, quelques relâchements propres à l'oral, peu de variation de construction. "
            "61-80 : vocabulaire précis, phrases construites, quelques images qui fonctionnent. "
            "81-100 : langue tenue et vivante, rythme des phrases travaillé, formules qui se retiennent."
        ),
    },
    "impact": {
        "label": "Impact",
        "question": "Le discours convainc-t-il, s'adresse-t-il à quelqu'un, laisse-t-il une trace ?",
        "anchors": (
            "0-20 : récitation sans destinataire, rien ne reste. "
            "21-40 : une intention perceptible, mais aucune adresse à l'auditoire. "
            "41-60 : on suit le propos sans être emporté, et une idée au moins reste à la fin. "
            "61-80 : adresse claire, montée en intensité, une formule qui reste. "
            "81-100 : on est tenu du début à la fin, la chute est mémorable."
        ),
    },
}

SYSTEM_PROMPT = f"""Tu es jury d'un concours d'éloquence francophone, spécialisé dans l'exercice du discours improvisé sur sujet imposé. Tu es exigeant et concret : ton retour doit être utilisable dès la prestation suivante.

NIVEAU DE RÉFÉRENCE — lis ceci avant de noter quoi que ce soit.
Tu évalues une improvisation de deux minutes, sans préparation, produite par une personne qui s'entraîne régulièrement. Ce n'est pas une finale de concours, et l'échelle doit refléter ce format :
- 50 = une prestation honnête pour l'exercice : le sujet est traité, le propos se suit, la langue est correcte. C'est le point médian normal, pas un aveu de faiblesse.
- 70 = nettement au-dessus de la moyenne des orateurs qui s'entraînent.
- 85 et plus = exceptionnel, ce qu'on retient d'une soirée entière.
- Moins de 30 = quelque chose a vraiment manqué, et tu dois pouvoir dire quoi en une phrase.
Noter sévèrement n'est pas noter juste. Une note basse doit signaler un vrai manque, pas l'écart entre un amateur et un finaliste.

GRILLE DE NOTATION (version {RUBRIC_VERSION}) — applique-la à la lettre, palier par palier :
{chr(10).join(f"- {name} ({a['label']}) : {a['question']} {a['anchors']}" for name, a in AXES.items())}

RÈGLES IMPÉRATIVES
1. Tu notes uniquement les cinq axes ci-dessus. Le débit, les pauses, les tics de langage (« euh », « du coup », « en fait »...) et l'intonation sont mesurés séparément par des outils acoustiques, et l'orateur reçoit déjà un retour automatique là-dessus. Ce n'est pas ton sujet.
   - Aucune de tes cinq notes ne doit monter ou descendre à cause d'un tic, d'un silence, d'un débit ou d'une intonation. L'axe « langue » juge la syntaxe, la précision du vocabulaire et le registre — pas la fluidité.
   - Ton axe prioritaire doit porter sur la pensée, la construction ou la langue. Répondre « réduis tes tics » ou « travaille ta fluidité » est interdit : c'est déjà dit, et ce n'est pas ton rôle. Tu es là pour ce qu'une machine ne sait pas mesurer.
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
    """Contexte factuel transmis au LLM — strictement limité à ce qui n'est PAS
    déjà noté ailleurs.

    Le débit, les pauses, les tics, la richesse lexicale et l'intonation entrent
    tous dans le score d'aisance calculé par le code. Les transmettre au modèle
    revenait à les faire compter une seconde fois : en version 1.0, il baissait
    la note de « langue » à cause des « du coup » et proposait « réduis tes
    tics » comme axe prioritaire, alors que les mesures le disaient déjà.

    Le durcir par une consigne n'a pas suffi — un modèle de petite taille ne
    tient pas une interdiction portant sur une donnée qu'il a sous les yeux. La
    seule correction fiable est de ne pas la lui donner. Une contrainte qu'on
    peut rendre structurelle vaut mieux qu'une contrainte qu'on demande.

    Ne reste donc ici que le cadrage temporel — utile pour juger si la
    conclusion a été bâclée ou le temps sous-exploité — et les mots
    sur-utilisés, qui relèvent de la langue et n'entrent dans aucun score.
    """

    lines = [
        f"- Durée du discours : {metrics.duration_s:.0f} s sur {time_limit_s} s imparties",
        f"- Nombre de mots prononcés : {metrics.word_count}",
        f"- Nombre de phrases : {metrics.sentence_count}",
    ]

    if metrics.overused_words:
        detail = ", ".join(f"« {w} » x{c}" for w, c in metrics.overused_words)
        lines.append(f"- Mots revenant le plus souvent : {detail}")

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
