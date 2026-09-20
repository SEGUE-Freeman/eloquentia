"""Banque de domaines et de sujets, et tirage aléatoire.

Deux principes de rédaction, qui conditionnent la qualité de l'exercice :

1. Un sujet doit contenir une tension. « La lecture » ne se discute pas ;
   « Faut-il finir un livre qu'on n'aime pas ? » oblige à prendre parti.
2. Un sujet doit être traitable sans connaissance spécialisée. L'exercice teste
   la capacité à penser debout, pas l'érudition.

Le tirage évite les répétitions récentes : retomber sur le même sujet deux fois
dans la semaine casse l'exercice, qui repose sur l'effet de surprise.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# Niveaux : sert à proposer une montée en difficulté plutôt qu'un tirage
# uniforme qui découragerait un débutant.
ECHAUFFEMENT = "echauffement"
STANDARD = "standard"
EXIGEANT = "exigeant"


@dataclass(frozen=True)
class Domain:
    key: str
    label: str
    # Libelle court affiche sur la roue : au-dela d'une douzaine de
    # caracteres, le texte deborde du secteur.
    short: str
    level: str
    color: str       # couleur du secteur sur la roue
    topics: tuple[str, ...]


DOMAINS: tuple[Domain, ...] = (
    Domain(
        key="societe", label="Société", short="Société", level=STANDARD, color="#E4572E",
        topics=(
            "Faut-il avoir le droit de ne pas être joignable ?",
            "La politesse est-elle une hypocrisie utile ?",
            "Peut-on encore changer d'avis en public ?",
            "Faut-il rendre le vote obligatoire ?",
            "L'anonymat en ligne protège-t-il ou détruit-il le débat ?",
            "La solitude est-elle devenue un problème politique ?",
            "Doit-on juger une œuvre à l'aune de son auteur ?",
            "La gentillesse est-elle une faiblesse ?",
            "Faut-il un permis pour devenir parent ?",
            "Le mérite existe-t-il vraiment ?",
        ),
    ),
    Domain(
        key="technologie", label="Technologie", short="Technologie", level=STANDARD, color="#4A90D9",
        topics=(
            "Faut-il avoir peur de l'intelligence artificielle ?",
            "Un algorithme peut-il être juste ?",
            "Le smartphone nous a-t-il rendus plus seuls ?",
            "Faut-il un droit à la déconnexion pour les enfants ?",
            "La technologie résoudra-t-elle les problèmes qu'elle a créés ?",
            "Peut-on encore vivre sans laisser de traces ?",
            "L'innovation vaut-elle toujours mieux que la tradition ?",
            "Faut-il ralentir le progrès technique ?",
            "Une machine peut-elle créer une œuvre d'art ?",
            "Qui doit répondre des erreurs d'un système automatisé ?",
        ),
    ),
    Domain(
        key="arts", label="Arts & Culture", short="Arts", level=STANDARD, color="#B25FAC",
        topics=(
            "Faut-il finir un livre qu'on n'aime pas ?",
            "L'art doit-il être utile ?",
            "Un chef-d'œuvre peut-il vieillir ?",
            "La culture doit-elle être gratuite ?",
            "Peut-on aimer une œuvre sans la comprendre ?",
            "Le mauvais goût existe-t-il ?",
            "Faut-il défendre les langues qui meurent ?",
            "La musique adoucit-elle vraiment les mœurs ?",
            "Une copie vaut-elle l'original ?",
            "Le silence est-il un art ?",
        ),
    ),
    Domain(
        key="histoire", label="Histoire", short="Histoire", level=EXIGEANT, color="#C99B38",
        topics=(
            "L'histoire se répète-t-elle ?",
            "Faut-il déboulonner les statues ?",
            "Les grands hommes font-ils l'histoire, ou l'inverse ?",
            "Peut-on juger le passé avec les valeurs du présent ?",
            "L'oubli est-il nécessaire à la paix ?",
            "Une révolution tient-elle jamais ses promesses ?",
            "Qui écrit l'histoire des vaincus ?",
            "Le progrès est-il une illusion moderne ?",
            "Les frontières sont-elles des accidents ou des nécessités ?",
            "Que doit-on aux générations qui nous ont précédés ?",
        ),
    ),
    Domain(
        key="economie", label="Économie & Travail", short="Économie", level=EXIGEANT, color="#2E9E8F",
        topics=(
            "Le travail doit-il donner un sens à la vie ?",
            "Faut-il plafonner les très hauts revenus ?",
            "La croissance est-elle encore un objectif défendable ?",
            "Peut-on être riche sans être coupable ?",
            "Faut-il payer les stages, tous les stages ?",
            "La semaine de quatre jours est-elle un progrès ou un luxe ?",
            "L'argent corrompt-il tout ce qu'il touche ?",
            "Faut-il un revenu universel ?",
            "L'entrepreneur est-il un héros moderne ?",
            "Peut-on encore promettre un emploi à vie ?",
        ),
    ),
    Domain(
        key="philosophie", label="Philosophie & Éthique", short="Philosophie", level=EXIGEANT, color="#7B68C9",
        topics=(
            "Peut-on être heureux sans être libre ?",
            "Faut-il toujours dire la vérité ?",
            "Le doute est-il une force ou une paralysie ?",
            "Avons-nous des devoirs envers ceux qui ne sont pas encore nés ?",
            "Peut-on pardonner l'impardonnable ?",
            "La justice et la loi disent-elles la même chose ?",
            "Sommes-nous responsables de ce que nous ignorons ?",
            "Le bonheur est-il un but ou un effet secondaire ?",
            "Peut-on vouloir ce qu'on ne désire pas ?",
            "L'égalité est-elle un idéal ou une illusion ?",
        ),
    ),
    Domain(
        key="environnement", label="Environnement", short="Écologie", level=STANDARD, color="#5FA85F",
        topics=(
            "Faut-il culpabiliser les individus pour sauver la planète ?",
            "L'écologie est-elle un luxe de riches ?",
            "Peut-on encore prendre l'avion sans se justifier ?",
            "La nature a-t-elle des droits ?",
            "Faut-il renoncer au confort ?",
            "La sobriété peut-elle être désirable ?",
            "Doit-on sacrifier des emplois pour le climat ?",
            "Les villes sont-elles la solution ou le problème ?",
            "Faut-il interdire ce qu'on ne peut pas réparer ?",
            "Que répondre à ceux qui disent qu'il est déjà trop tard ?",
        ),
    ),
    Domain(
        key="education", label="Éducation", short="Éducation", level=STANDARD, color="#D9705B",
        topics=(
            "Faut-il noter les élèves ?",
            "L'école doit-elle apprendre à obéir ou à contester ?",
            "Peut-on enseigner le courage ?",
            "Faut-il interdire le téléphone à l'école ?",
            "L'échec est-il formateur ou destructeur ?",
            "Doit-on apprendre par cœur ?",
            "Les diplômes valent-ils encore quelque chose ?",
            "Faut-il enseigner la prise de parole dès l'école primaire ?",
            "Un professeur doit-il être aimé ?",
            "Apprend-on mieux seul ou à plusieurs ?",
        ),
    ),
    Domain(
        key="monde", label="Géopolitique & Monde", short="Monde", level=EXIGEANT, color="#3F7CAC",
        topics=(
            "Une frontière peut-elle être juste ?",
            "Le développement doit-il suivre le modèle occidental ?",
            "L'aide internationale aide-t-elle vraiment ?",
            "La souveraineté a-t-elle encore un sens ?",
            "Faut-il commercer avec des régimes qu'on désapprouve ?",
            "La diaspora est-elle une perte ou une force ?",
            "Les langues étrangères sont-elles une richesse ou une dépendance ?",
            "Peut-on rester neutre ?",
            "Le sport peut-il réconcilier les nations ?",
            "À qui appartiennent les ressources naturelles ?",
        ),
    ),
    Domain(
        key="quotidien", label="Vie quotidienne", short="Quotidien", level=ECHAUFFEMENT, color="#E8A33D",
        topics=(
            "Le meilleur repas que vous ayez jamais mangé.",
            "Faut-il arriver en avance ?",
            "Une chose que vous avez apprise trop tard.",
            "Les listes servent-elles à quelque chose ?",
            "Défendez le fait de ne rien faire.",
            "Le trajet compte-t-il plus que la destination ?",
            "Une habitude dont vous êtes secrètement fier.",
            "Faut-il répondre aux messages tout de suite ?",
            "Le désordre est-il un défaut ?",
            "Convainquez-nous de vous prêter dix mille francs.",
        ),
    ),
    Domain(
        key="carte_blanche", label="Carte blanche", short="Carte blanche", level=ECHAUFFEMENT, color="#D64550",
        topics=(
            "Faites l'éloge du lundi.",
            "Plaidez pour la cause du moustique.",
            "Expliquez la pluie à quelqu'un qui ne l'a jamais vue.",
            "Défendez une idée à laquelle vous ne croyez pas.",
            "Improvisez le discours d'adieu d'un objet cassé.",
            "Vendez-nous le silence.",
            "Faites l'éloge funèbre de votre ancienne version.",
            "Racontez une guerre entre deux mots.",
            "Justifiez un mensonge que vous avez dit enfant.",
            "Convainquez un extraterrestre de rester.",
        ),
    ),
)

DOMAINS_BY_KEY = {d.key: d for d in DOMAINS}


def draw_domain(
    exclude: list[str] | None = None,
    level: str | None = None,
    rng: random.Random | None = None,
) -> Domain:
    """Tire un domaine, en évitant ceux tirés récemment."""
    rng = rng or random.Random()
    exclude = set(exclude or [])

    pool = [d for d in DOMAINS if level is None or d.level == level]
    remaining = [d for d in pool if d.key not in exclude]
    # Si tout a été exclu, on repart du pool complet plutôt que d'échouer.
    return rng.choice(remaining or pool)


def draw_topic(
    domain: Domain,
    exclude: list[str] | None = None,
    rng: random.Random | None = None,
) -> str:
    rng = rng or random.Random()
    exclude = set(exclude or [])
    remaining = [t for t in domain.topics if t not in exclude]
    return rng.choice(remaining or list(domain.topics))


def draw(
    recent_domains: list[str] | None = None,
    recent_topics: list[str] | None = None,
    level: str | None = None,
    rng: random.Random | None = None,
) -> tuple[Domain, str]:
    """Tirage complet : un domaine, puis un sujet dans ce domaine."""
    rng = rng or random.Random()
    domain = draw_domain(exclude=recent_domains, level=level, rng=rng)
    return domain, draw_topic(domain, exclude=recent_topics, rng=rng)


class UnknownTopic(LookupError):
    pass


def resolve(domain_key: str, topic_index: int) -> tuple[Domain, str]:
    """Retrouve le sujet canonique à partir de son identifiant.

    Le client ne renvoie jamais le texte du sujet, seulement sa référence. Deux
    problèmes disparaissent d'un coup : le texte ne peut plus être altéré en
    route (encodage, troncature), et le sujet enregistré avec la session ne peut
    plus diverger de celui qui a été tiré.
    """
    domain = DOMAINS_BY_KEY.get(domain_key)
    if domain is None:
        raise UnknownTopic(f"Domaine inconnu : {domain_key}")
    if not 0 <= topic_index < len(domain.topics):
        raise UnknownTopic(f"Sujet inconnu dans {domain_key} : {topic_index}")
    return domain, domain.topics[topic_index]


def wheel_payload() -> list[dict]:
    """Description des secteurs, consommée par la roue côté front.

    Les sujets sont inclus pour l'animation du second tirage : le défilement
    rapide qui rend visible le hasard à l'intérieur du domaine. Ils ne sont pas
    confidentiels — les parcourir à l'avance ne fait que gâcher son propre
    exercice.
    """
    return [
        {
            "key": d.key,
            "label": d.label,
            "level": d.level,
            "color": d.color,
            "short": d.short,
            "topic_count": len(d.topics),
            "topics": list(d.topics),
        }
        for d in DOMAINS
    ]
