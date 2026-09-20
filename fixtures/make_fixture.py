"""Génère une transcription de test avec horodatage mot à mot.

Sert à développer les métriques et les prompts sans dépenser un appel d'API à
chaque itération. Les timestamps sont SYNTHÉTIQUES : ils imitent un rythme de
parole plausible (durée proportionnelle à la longueur du mot, respiration après
la ponctuation, hésitation allongée sur les tics). Ils ne remplacent pas une
validation sur de vrais enregistrements.

Usage : python fixtures/make_fixture.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Rythme de base, calé sur un débit français d'environ 160 mots/min.
BASE_WORD_S = 0.085
PER_CHAR_S = 0.048
PAUSE_COMMA_S = 0.28
PAUSE_PERIOD_S = 0.62
HESITATION_EXTRA_S = 0.45

HESITATIONS = {"euh", "heu", "hum", "bah", "ben"}

# Marqueur explicite pour placer un silence long : [[1.9]]
PAUSE_MARKER = re.compile(r"\[\[([0-9.]+)\]\]")


# Discours d'entraînement type : 2 minutes, sujet imposé, avec les défauts
# réels d'un orateur qui progresse (tics, une perte de fil, des répétitions).
DEMO_SPEECH = """
Euh, alors, le sujet qui m'est tombé dessus, c'est : faut-il avoir peur de
l'intelligence artificielle ? [[1.2]] Du coup, je vais vous dire tout de suite
ce que j'en pense : la vraie question n'est pas d'avoir peur de la machine,
elle est de savoir qui la tient.

En fait, quand on regarde l'histoire, euh, c'est toujours la même chose. Au
dix-neuvième siècle, les ouvriers anglais cassaient les métiers à tisser. On
les a appelés les luddites. Ils n'avaient pas peur du tissu, ils avaient peur
de perdre leur salaire. [[0.9]] Et la machine, du coup, n'était qu'un prétexte.

Aujourd'hui, c'est pareil, voilà, sauf que la machine écrit, dessine, et
répond. Euh. [[2.4]] Pardon. Ce que je voulais dire, c'est que le danger
n'est pas que l'intelligence artificielle pense, c'est qu'elle décide à notre
place sans qu'on s'en aperçoive.

Un exemple concret : quand une banque refuse un crédit à cause d'un score
calculé par un algorithme, personne ne peut expliquer le refus. Le client n'a
personne à qui parler. Et ça, c'est un problème, c'est un vrai problème de
démocratie, pas un problème de technologie.

Du coup, ma position, en fait, c'est qu'il ne faut pas avoir peur, il faut
exiger. Exiger de savoir quand une décision vient d'une machine. Exiger
qu'un humain puisse la corriger. [[0.8]] La peur, elle nous fait reculer.
L'exigence, elle nous fait avancer.

Voilà. Merci.
"""


def synthesize(text: str) -> dict:
    words = []
    t = 0.35  # petit blanc avant de commencer à parler

    for raw in text.split():
        marker = PAUSE_MARKER.fullmatch(raw)
        if marker:
            t += float(marker.group(1))
            continue

        clean = raw.strip()
        core = re.sub(r"[^\w'’-]", "", clean, flags=re.UNICODE)
        if not core:
            # La typographie française sépare « ? », « : » et « ! » du mot qui
            # précède. Ces signes isolés doivent être recollés au mot précédent,
            # sinon la ponctuation disparaît de la transcription et le découpage
            # en phrases devient faux.
            if clean and words:
                words[-1]["word"] += clean
                if clean[-1] in ".!?":
                    t += PAUSE_PERIOD_S
                elif clean[-1] in ",;:":
                    t += PAUSE_COMMA_S
            continue

        duration = BASE_WORD_S + PER_CHAR_S * len(core)
        if core.lower().strip(",.") in HESITATIONS:
            duration += HESITATION_EXTRA_S

        words.append({"word": clean, "start": round(t, 3), "end": round(t + duration, 3)})
        t += duration

        if clean.endswith((".", "!", "?")):
            t += PAUSE_PERIOD_S
        elif clean.endswith((",", ";", ":")):
            t += PAUSE_COMMA_S
        else:
            t += 0.04  # liaison entre deux mots

    return {
        "text": " ".join(w["word"] for w in words),
        "words": words,
        "language": "fr",
        "duration": round(t + 0.4, 2),
    }


# Même orateur, quelques séances plus tard : tics presque éliminés, plan
# annoncé, exemples plus précis. Sert à vérifier que la progression se voit
# dans les chiffres et pas seulement dans le commentaire.
DEMO_SPEECH_PROGRESSED = """
Faut-il avoir peur de l'intelligence artificielle ? [[1.1]] Je vais vous
répondre en trois temps : ce que nous craignons, ce que nous risquons
vraiment, et ce que nous devons exiger.

Ce que nous craignons, d'abord. En mil huit cent onze, des ouvriers anglais
brisent les métiers à tisser de Nottingham. On les appelle les luddites.
[[0.7]] Ils ne détestaient pas le tissu. Ils refusaient de perdre leur salaire
sans avoir eu voix au chapitre. La machine n'était que le visage visible d'une
décision prise sans eux.

Ce que nous risquons, ensuite. Aujourd'hui, un algorithme refuse un crédit, et
personne dans l'agence ne sait expliquer pourquoi. Le client repart sans motif
et sans recours. [[0.9]] Le danger n'est pas qu'une machine pense. Il est
qu'elle décide, et que plus personne ne réponde de cette décision.

Ce que nous devons exiger, enfin. Trois choses simples : savoir quand une
décision vient d'un algorithme, obtenir la raison de cette décision, et
pouvoir la faire réexaminer par un humain. [[0.8]]

La peur nous fait reculer devant l'outil. L'exigence nous fait tenir la main
qui le tient. Je préfère la seconde. Merci.
"""


if __name__ == "__main__":
    for speech, name in (
        (DEMO_SPEECH, "transcript_demo.json"),
        (DEMO_SPEECH_PROGRESSED, "transcript_demo_2.json"),
    ):
        payload = synthesize(PAUSE_MARKER.sub(lambda m: f" [[{m.group(1)}]] ", speech))
        out = Path(__file__).parent / name
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{out.name} : {len(payload['words'])} mots, {payload['duration']:.1f} s")
