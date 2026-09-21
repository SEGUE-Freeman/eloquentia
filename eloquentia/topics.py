"""Banque de domaines, de sujets et de ressources, et tirage aléatoire.

Deux principes de rédaction des sujets, qui conditionnent la qualité de
l'exercice :

1. Un sujet doit contenir une tension. « La lecture » ne se discute pas ;
   « Faut-il finir un livre qu'on n'aime pas ? » oblige à prendre parti.
2. Un sujet doit être traitable sans connaissance spécialisée. L'exercice teste
   la capacité à penser debout, pas l'érudition.

Le tirage évite les répétitions récentes : retomber sur le même sujet deux fois
dans la semaine casse l'exercice, qui repose sur l'effet de surprise.

Les ressources sont **écrites à la main**, jamais générées. Un modèle de langue
invente des titres et des auteurs plausibles avec un aplomb total ; recommander
un livre qui n'existe pas serait pire que ne rien recommander, surtout sur une
plateforme dont l'objet est la culture générale.
"""

from __future__ import annotations

import random
import re
import unicodedata
from dataclasses import dataclass

# Niveaux : sert à proposer une montée en difficulté plutôt qu'un tirage
# uniforme qui découragerait un débutant.
ECHAUFFEMENT = "echauffement"
STANDARD = "standard"
EXIGEANT = "exigeant"

LIVRE = "livre"
ESSAI = "essai"
ROMAN = "roman"
VIDEO = "vidéo"
FILM = "film"
PODCAST = "podcast"


@dataclass(frozen=True)
class Resource:
    """Une référence pour nourrir un sujet.

    Pas d'URL volontairement : les liens meurent, et une adresse inventée est
    pire qu'absente. Le titre et l'auteur suffisent à retrouver l'œuvre, et
    l'interface en fait un lien de recherche.
    """

    kind: str
    title: str
    author: str
    note: str                       # une ligne : ce qu'on y trouve
    tags: tuple[str, ...] = ()      # mots-clés pour le rapprochement au sujet


@dataclass(frozen=True)
class Domain:
    key: str
    label: str
    # Libellé court affiché sur la roue : au-delà d'une douzaine de
    # caractères, le texte déborde du secteur.
    short: str
    level: str
    color: str
    topics: tuple[str, ...]
    resources: tuple[Resource, ...] = ()


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
            "La honte est-elle utile à une société ?",
            "Faut-il pardonner publiquement ?",
            "Les traditions méritent-elles d'être défendues parce qu'elles sont anciennes ?",
            "Peut-on encore vivre sans se comparer aux autres ?",
            "L'égalité des chances est-elle une promesse tenable ?",
            "Faut-il se méfier de ceux qui ne doutent jamais ?",
        ),
        resources=(
            Resource(ESSAI, "La Distinction", "Pierre Bourdieu",
                     "Comment les goûts trahissent la position sociale.",
                     ("mérite", "classe", "goût", "égalité", "comparer")),
            Resource(ESSAI, "Surveiller et punir", "Michel Foucault",
                     "La naissance de la surveillance comme forme de pouvoir.",
                     ("anonymat", "surveillance", "honte", "punir", "pouvoir")),
            Resource(ESSAI, "La Société du spectacle", "Guy Debord",
                     "L'image remplace le vécu, et le vécu devient représentation.",
                     ("public", "image", "spectacle", "comparer")),
            Resource(ESSAI, "Bowling Alone", "Robert Putnam",
                     "L'effondrement du lien social mesuré sur cinquante ans.",
                     ("solitude", "lien", "communauté", "politique")),
            Resource(ROMAN, "Les Misérables", "Victor Hugo",
                     "Le pardon comme force politique, à travers Jean Valjean.",
                     ("pardon", "justice", "honte", "misère")),
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
            "Faut-il apprendre à coder à tout le monde ?",
            "La mémoire numérique nous dispense-t-elle de retenir ?",
            "Doit-on avoir le droit d'être oublié d'Internet ?",
            "Les réseaux sociaux sont-ils responsables de ce qu'on y lit ?",
            "Une intelligence artificielle peut-elle nous comprendre ?",
            "Faut-il craindre de dépendre d'outils qu'on ne sait pas réparer ?",
        ),
        resources=(
            Resource(ESSAI, "Algorithmes : la bombe à retardement", "Cathy O'Neil",
                     "Comment des modèles opaques décident de crédits et d'embauches.",
                     ("algorithme", "juste", "automatisé", "erreur", "décision")),
            Resource(ROMAN, "Le Meilleur des mondes", "Aldous Huxley",
                     "Une société pacifiée par la technique, au prix de la liberté.",
                     ("progrès", "peur", "innovation", "dépendance")),
            Resource(ESSAI, "Homo Deus", "Yuval Noah Harari",
                     "Ce que devient l'humain quand la machine décide mieux que lui.",
                     ("intelligence", "artificielle", "comprendre", "avenir")),
            Resource(PODCAST, "Le Code a changé", "Xavier de La Porte, France Inter",
                     "Enquêtes courtes sur ce que le numérique fait à nos vies.",
                     ("smartphone", "réseaux", "seuls", "traces", "oubli")),
            Resource(ESSAI, "La Convivialité", "Ivan Illich",
                     "Plaidoyer pour des outils qu'on maîtrise au lieu de les subir.",
                     ("réparer", "dépendre", "outil", "ralentir", "coder")),
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
            "Faut-il tout montrer sur scène ?",
            "L'artiste doit-il souffrir ?",
            "Une œuvre a-t-elle un sens que son auteur ignore ?",
            "Faut-il relire ou découvrir ?",
            "La critique sert-elle à quelque chose ?",
            "L'ennui est-il nécessaire à la création ?",
        ),
        resources=(
            Resource(ESSAI, "L'Œuvre d'art à l'époque de sa reproductibilité technique",
                     "Walter Benjamin",
                     "Ce que la copie fait disparaître de l'original.",
                     ("copie", "original", "chef-d'œuvre", "reproduction")),
            Resource(VIDEO, "Ways of Seeing", "John Berger, série BBC",
                     "Quatre épisodes qui changent la façon de regarder une image.",
                     ("comprendre", "regard", "goût", "critique")),
            Resource(ESSAI, "Le Degré zéro de l'écriture", "Roland Barthes",
                     "L'écriture comme choix, et le sens qui échappe à l'auteur.",
                     ("auteur", "sens", "ignore", "écriture")),
            Resource(LIVRE, "Comme un roman", "Daniel Pennac",
                     "Les droits imprescriptibles du lecteur, dont celui de ne pas finir.",
                     ("livre", "finir", "lire", "relire", "ennui")),
            Resource(ESSAI, "Le Silence", "John Cage (conférences réunies)",
                     "Le compositeur de 4'33'' sur le son, l'absence et l'attention.",
                     ("silence", "musique", "art")),
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
            "Faut-il commémorer les défaites ?",
            "Les archives disent-elles la vérité ?",
            "Peut-on réparer une injustice vieille de deux siècles ?",
            "L'histoire est-elle une science ou un récit ?",
            "Les empires meurent-ils toujours de la même façon ?",
            "Doit-on enseigner les pages honteuses d'un pays ?",
        ),
        resources=(
            Resource(ESSAI, "Apologie pour l'histoire", "Marc Bloch",
                     "Un historien résistant explique son métier, en prison.",
                     ("science", "récit", "archives", "vérité", "métier")),
            Resource(ESSAI, "Les Lieux de mémoire", "Pierre Nora",
                     "Comment une nation fabrique ce dont elle se souvient.",
                     ("statues", "commémorer", "mémoire", "oubli", "défaites")),
            Resource(ESSAI, "Sapiens", "Yuval Noah Harari",
                     "Une histoire de l'humanité par ses récits collectifs.",
                     ("progrès", "empires", "récit", "générations")),
            Resource(ESSAI, "Les Damnés de la terre", "Frantz Fanon",
                     "L'histoire vue depuis les colonisés, pas depuis les vainqueurs.",
                     ("vaincus", "injustice", "réparer", "honteuses", "empires")),
            Resource(ESSAI, "L'Étrange Défaite", "Marc Bloch",
                     "Une nation qui s'effondre, analysée à chaud par un témoin.",
                     ("défaites", "juger", "passé")),
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
            "Faut-il travailler moins ou travailler autrement ?",
            "Le bénévolat est-il un travail ?",
            "Doit-on choisir son métier par passion ?",
            "La retraite est-elle une invention heureuse ?",
            "Un prix dit-il la valeur d'une chose ?",
            "Faut-il avoir honte de négocier son salaire ?",
        ),
        resources=(
            Resource(ESSAI, "Le Capital au XXIe siècle", "Thomas Piketty",
                     "Deux siècles de données sur qui possède quoi.",
                     ("revenus", "riche", "plafonner", "inégalité")),
            Resource(ESSAI, "Bullshit Jobs", "David Graeber",
                     "Sur les emplois que ceux qui les occupent jugent inutiles.",
                     ("travail", "sens", "métier", "autrement", "bénévolat")),
            Resource(ESSAI, "La Grande Transformation", "Karl Polanyi",
                     "Comment le marché s'est détaché de la société qui le portait.",
                     ("argent", "prix", "valeur", "croissance")),
            Resource(ESSAI, "Éloge de la lenteur", "Carl Honoré",
                     "Enquête sur ceux qui ont décidé de ralentir la cadence.",
                     ("quatre", "jours", "moins", "retraite", "temps")),
            Resource(ROMAN, "Germinal", "Émile Zola",
                     "Le travail, la grève et la dignité, vus d'en bas.",
                     ("travail", "emploi", "salaire", "honte")),
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
            "Faut-il craindre la mort ?",
            "Peut-on se connaître soi-même ?",
            "La liberté est-elle un fardeau ?",
            "Une vie sans épreuve vaut-elle d'être vécue ?",
            "Le courage s'apprend-il ?",
            "Faut-il obéir à une loi qu'on juge injuste ?",
        ),
        resources=(
            Resource(LIVRE, "Lettres à Lucilius", "Sénèque",
                     "Des lettres brèves sur la mort, le temps et ce qui dépend de nous.",
                     ("mort", "craindre", "bonheur", "épreuve", "temps")),
            Resource(LIVRE, "Les Essais", "Michel de Montaigne",
                     "Un homme qui doute en public, et en fait une méthode.",
                     ("doute", "connaître", "soi-même", "vérité")),
            Resource(ESSAI, "Le Mythe de Sisyphe", "Albert Camus",
                     "Que faire d'une vie dont le sens n'est pas donné d'avance.",
                     ("bonheur", "vie", "vécue", "liberté", "fardeau")),
            Resource(LIVRE, "Éthique à Nicomaque", "Aristote",
                     "Le courage et la justice comme habitudes qui s'acquièrent.",
                     ("courage", "apprend", "justice", "vertu")),
            Resource(ESSAI, "La Désobéissance civile", "Henry David Thoreau",
                     "Pourquoi un citoyen peut refuser d'obéir, et à quel prix.",
                     ("obéir", "loi", "injuste", "responsable")),
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
            "L'humanité est-elle une espèce parmi d'autres ?",
            "Faut-il rendre des comptes aux générations futures ?",
            "Peut-on aimer la nature sans la connaître ?",
            "La croissance verte existe-t-elle ?",
            "Faut-il un permis pour polluer ?",
            "Le progrès technique nous sauvera-t-il du climat ?",
        ),
        resources=(
            Resource(ESSAI, "Printemps silencieux", "Rachel Carson",
                     "Le livre de 1962 qui a fait naître l'écologie moderne.",
                     ("nature", "pollution", "polluer", "espèce")),
            Resource(ESSAI, "Où atterrir ?", "Bruno Latour",
                     "Penser le climat comme une question politique, pas morale.",
                     ("politique", "climat", "culpabiliser", "atterrir")),
            Resource(FILM, "Home", "Yann Arthus-Bertrand",
                     "La planète vue du ciel, et ce que l'humain y a changé.",
                     ("planète", "nature", "villes", "tard")),
            Resource(ESSAI, "Effondrement", "Jared Diamond",
                     "Pourquoi des sociétés entières ont choisi leur propre ruine.",
                     ("tard", "sobriété", "renoncer", "futures")),
            Resource(ESSAI, "La Vie secrète des arbres", "Peter Wohlleben",
                     "Connaître la forêt de près, pour cesser de la voir comme un décor.",
                     ("nature", "connaître", "aimer", "arbres")),
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
            "Faut-il laisser les enfants s'ennuyer ?",
            "L'école peut-elle corriger les inégalités ?",
            "Doit-on apprendre une chose inutile ?",
            "La discipline est-elle l'ennemie de la curiosité ?",
            "Faut-il enseigner ce qui fâche ?",
            "Peut-on apprendre sans maître ?",
        ),
        resources=(
            Resource(ESSAI, "Pédagogie des opprimés", "Paulo Freire",
                     "Enseigner comme un acte de libération, pas de remplissage.",
                     ("obéir", "contester", "inégalités", "opprimés")),
            Resource(ESSAI, "Le Maître ignorant", "Jacques Rancière",
                     "Un professeur qui enseigne ce qu'il ne sait pas — et ça marche.",
                     ("maître", "professeur", "seul", "apprendre")),
            Resource(ESSAI, "Les Héritiers", "Pierre Bourdieu et Jean-Claude Passeron",
                     "Ce que l'école reproduit sans le dire.",
                     ("inégalités", "diplômes", "noter", "héritiers")),
            Resource(LIVRE, "Apprendre !", "Stanislas Dehaene",
                     "Ce que les sciences cognitives disent vraiment de la mémorisation.",
                     ("cœur", "mémoire", "apprend", "échec", "attention")),
            Resource(LIVRE, "Chagrin d'école", "Daniel Pennac",
                     "Le récit d'un cancre devenu professeur.",
                     ("échec", "professeur", "aimé", "ennuyer")),
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
            "Faut-il rendre les œuvres prises pendant la colonisation ?",
            "Une puissance peut-elle être morale ?",
            "L'exil est-il toujours une perte ?",
            "Faut-il craindre les blocs ou les regretter ?",
            "La paix se négocie-t-elle avec ceux qu'on méprise ?",
            "Un pays peut-il se développer seul ?",
        ),
        resources=(
            Resource(ESSAI, "L'Orientalisme", "Edward Saïd",
                     "Comment l'Occident a fabriqué l'Orient qu'il voulait voir.",
                     ("occidental", "modèle", "développement", "regard")),
            Resource(ESSAI, "Les Veines ouvertes de l'Amérique latine", "Eduardo Galeano",
                     "Cinq siècles d'extraction, racontés depuis les extraits.",
                     ("ressources", "naturelles", "développement", "aide")),
            Resource(ESSAI, "Peau noire, masques blancs", "Frantz Fanon",
                     "Ce que la domination fait à la langue et à l'image de soi.",
                     ("langues", "dépendance", "diaspora", "exil")),
            Resource(ESSAI, "Le Choc des civilisations", "Samuel Huntington",
                     "Une thèse très discutée, utile à connaître pour la contester.",
                     ("blocs", "frontière", "puissance", "paix")),
            Resource(ROMAN, "L'Étranger", "Albert Camus",
                     "L'étrangeté au monde, et ce qu'un regard colonial ne voit pas.",
                     ("exil", "neutre", "étranger")),
        ),
    ),
    Domain(
        key="afrique", label="Afrique & Francophonie", short="Afrique", level=STANDARD, color="#E8734A",
        topics=(
            "La francophonie est-elle une chance ou un héritage encombrant ?",
            "Faut-il enseigner dans les langues maternelles ?",
            "La tradition est-elle un frein ou une ressource ?",
            "Partir est-il une trahison ?",
            "L'Afrique doit-elle écrire elle-même son histoire ?",
            "Le développement passe-t-il par la ville ou par le village ?",
            "Faut-il des quotas pour les femmes en politique ?",
            "La jeunesse est-elle une richesse ou une bombe ?",
            "Peut-on bâtir sans imiter ?",
            "Les frontières héritées doivent-elles être redessinées ?",
            "La réussite oblige-t-elle envers les siens ?",
            "Faut-il se méfier de ceux qui viennent investir ?",
            "L'oralité vaut-elle l'écrit ?",
            "Doit-on parler la langue de l'autre pour être entendu ?",
            "L'unité africaine est-elle un rêve utile ?",
            "Qu'est-ce qu'on doit à son village ?",
        ),
        resources=(
            Resource(ROMAN, "L'Aventure ambiguë", "Cheikh Hamidou Kane",
                     "Un jeune Sénégalais entre l'école coranique et l'école française.",
                     ("langues", "tradition", "école", "partir", "imiter")),
            Resource(ROMAN, "Les Soleils des indépendances", "Ahmadou Kourouma",
                     "Le français malinké d'un prince déchu par l'indépendance.",
                     ("oralité", "langue", "tradition", "histoire")),
            Resource(ROMAN, "Une si longue lettre", "Mariama Bâ",
                     "Une veuve sénégalaise écrit ce qu'elle n'a jamais pu dire.",
                     ("femmes", "tradition", "siens", "quotas")),
            Resource(ESSAI, "Critique de la raison nègre", "Achille Mbembe",
                     "Penser l'Afrique au présent, sans la réduire à sa blessure.",
                     ("histoire", "écrire", "unité", "identité")),
            Resource(ROMAN, "Petit pays", "Gaël Faye",
                     "L'enfance, l'exil et la langue, entre Burundi et France.",
                     ("partir", "exil", "trahison", "village", "jeunesse")),
        ),
    ),
    Domain(
        key="sciences", label="Sciences", short="Sciences", level=EXIGEANT, color="#39A0B8",
        topics=(
            "La science peut-elle tout expliquer ?",
            "Faut-il croire les experts ?",
            "Une théorie fausse peut-elle être utile ?",
            "Doit-on chercher sans savoir à quoi ça sert ?",
            "Le hasard existe-t-il vraiment ?",
            "Faut-il des limites à la recherche ?",
            "La science est-elle neutre ?",
            "Peut-on démontrer qu'on a tort ?",
            "Le vivant est-il une machine ?",
            "Faut-il vulgariser au risque de simplifier ?",
            "L'intuition a-t-elle sa place en science ?",
            "Une découverte appartient-elle à son auteur ?",
            "Faut-il financer l'exploration spatiale ?",
            "Le doute scientifique nourrit-il le complotisme ?",
            "La nature a-t-elle des lois, ou seulement des habitudes ?",
            "Peut-on faire confiance à ce qu'on ne comprend pas ?",
        ),
        resources=(
            Resource(ESSAI, "La Structure des révolutions scientifiques", "Thomas Kuhn",
                     "Pourquoi la science avance par ruptures et non par accumulation.",
                     ("théorie", "fausse", "tort", "révolution", "paradigme")),
            Resource(ESSAI, "Le Hasard et la Nécessité", "Jacques Monod",
                     "Un biologiste Nobel sur le hasard au cœur du vivant.",
                     ("hasard", "vivant", "machine", "nature")),
            Resource(LIVRE, "Une brève histoire du temps", "Stephen Hawking",
                     "La vulgarisation comme exercice de style, réussi.",
                     ("vulgariser", "simplifier", "espace", "spatiale")),
            Resource(VIDEO, "ScienceEtonnante", "David Louapre",
                     "Chaîne francophone qui explique sans abîmer.",
                     ("vulgariser", "expliquer", "comprendre", "experts")),
            Resource(ESSAI, "Cosmos", "Carl Sagan",
                     "Le doute méthodique présenté comme une vertu morale.",
                     ("doute", "complotisme", "experts", "confiance")),
        ),
    ),
    Domain(
        key="medias", label="Médias & Information", short="Médias", level=STANDARD, color="#C2569A",
        topics=(
            "Une information gratuite peut-elle être libre ?",
            "Faut-il montrer les images de la violence ?",
            "Le journaliste doit-il être neutre ?",
            "Peut-on s'informer en trois minutes ?",
            "Faut-il répondre aux fausses nouvelles ?",
            "L'opinion vaut-elle l'information ?",
            "Doit-on nommer les coupables ?",
            "La transparence est-elle toujours un bien ?",
            "Peut-on se passer de journaux ?",
            "Le direct nous informe-t-il ou nous affole-t-il ?",
            "Faut-il protéger le public de lui-même ?",
            "Une rumeur peut-elle dire vrai ?",
            "Le silence des médias est-il une prise de position ?",
            "Faut-il écouter ceux qui nous exaspèrent ?",
            "La vitesse est-elle l'ennemie de la vérité ?",
            "Un titre a-t-il le droit d'exagérer ?",
        ),
        resources=(
            Resource(ESSAI, "La Fabrication du consentement",
                     "Edward Herman et Noam Chomsky",
                     "Comment une presse libre peut servir un discours unique.",
                     ("neutre", "libre", "gratuite", "opinion", "consentement")),
            Resource(ESSAI, "Se distraire à en mourir", "Neil Postman",
                     "Quand l'information devient un divertissement, elle cesse d'informer.",
                     ("direct", "trois", "minutes", "vitesse", "divertissement")),
            Resource(ESSAI, "Sur la télévision", "Pierre Bourdieu",
                     "Deux conférences sur l'urgence comme censure invisible.",
                     ("vitesse", "direct", "titre", "télévision")),
            Resource(ESSAI, "L'Opinion publique", "Walter Lippmann",
                     "Le décalage entre le monde réel et les images qu'on en a.",
                     ("opinion", "public", "rumeur", "vérité")),
            Resource(FILM, "Les Hommes du président", "Alan J. Pakula",
                     "Le Watergate : ce que vérifier une information coûte vraiment.",
                     ("coupables", "nommer", "enquête", "transparence")),
        ),
    ),
    Domain(
        key="relations", label="Relations humaines", short="Relations", level=STANDARD, color="#D94F70",
        topics=(
            "L'amitié se choisit-elle vraiment ?",
            "Faut-il tout dire à ceux qu'on aime ?",
            "Peut-on aimer sans admirer ?",
            "La jalousie prouve-t-elle l'amour ?",
            "Faut-il rester fidèle à ses amis d'enfance ?",
            "Peut-on vivre sans être aimé ?",
            "La famille est-elle un choix ou un destin ?",
            "Faut-il savoir rompre ?",
            "Le couple est-il une institution dépassée ?",
            "Peut-on pardonner une trahison ?",
            "Faut-il dire à quelqu'un qu'il se trompe ?",
            "L'amour est-il un travail ?",
            "Peut-on être soi-même avec tout le monde ?",
            "Faut-il craindre ceux qui nous ressemblent ?",
            "La distance rapproche-t-elle ?",
            "Doit-on aimer ses parents ?",
        ),
        resources=(
            Resource(ESSAI, "Fragments d'un discours amoureux", "Roland Barthes",
                     "L'amour décomposé en figures : l'attente, la jalousie, l'absence.",
                     ("amour", "jalousie", "distance", "attente")),
            Resource(ESSAI, "L'Art d'aimer", "Erich Fromm",
                     "Thèse centrale : aimer est une compétence, pas une chance.",
                     ("amour", "travail", "aimer", "couple")),
            Resource(LIVRE, "De l'amitié", "Michel de Montaigne",
                     "Quelques pages sur La Boétie, insurpassées depuis.",
                     ("amitié", "amis", "enfance", "choisit")),
            Resource(ROMAN, "Les Liaisons dangereuses", "Choderlos de Laclos",
                     "La manipulation amoureuse portée à la perfection.",
                     ("trahison", "pardonner", "rompre", "manipulation")),
            Resource(ROMAN, "Le Nœud de vipères", "François Mauriac",
                     "Une famille comme destin dont on ne se défait pas.",
                     ("famille", "destin", "parents", "rancune")),
        ),
    ),
    Domain(
        key="sport", label="Sport", short="Sport", level=ECHAUFFEMENT, color="#4FA36B",
        topics=(
            "Le sport rend-il meilleur ?",
            "Faut-il vouloir gagner à tout prix ?",
            "Un champion doit-il être un exemple ?",
            "La défaite apprend-elle plus que la victoire ?",
            "Le sport professionnel est-il encore du sport ?",
            "Faut-il séparer l'athlète de son pays ?",
            "Le talent excuse-t-il tout ?",
            "Peut-on aimer un sport qu'on ne pratique pas ?",
            "L'entraînement tue-t-il le plaisir ?",
            "Faut-il des héros ?",
            "Le supporter fait-il partie du jeu ?",
            "Doit-on organiser des compétitions dans les régimes autoritaires ?",
            "Le corps a-t-il des limites qu'il faut respecter ?",
            "Peut-on perdre avec élégance ?",
            "L'esprit d'équipe s'enseigne-t-il ?",
            "Faut-il arrêter au sommet ?",
        ),
        resources=(
            Resource(LIVRE, "Open", "André Agassi",
                     "Une autobiographie qui commence par : je déteste le tennis.",
                     ("champion", "plaisir", "entraînement", "arrêter", "sommet")),
            Resource(ROMAN, "Courir", "Jean Echenoz",
                     "La vie d'Emil Zátopek, entre exploit et régime politique.",
                     ("athlète", "pays", "autoritaires", "héros")),
            Resource(VIDEO, "The Last Dance", "Documentaire, ESPN/Netflix",
                     "Dix épisodes sur l'obsession de gagner et son coût.",
                     ("gagner", "prix", "équipe", "exemple")),
            Resource(LIVRE, "Le Combat du siècle", "Norman Mailer",
                     "Ali contre Foreman à Kinshasa, par un écrivain sur place.",
                     ("défaite", "victoire", "héros", "boxe")),
            Resource(ESSAI, "Éloge du mauvais geste", "Recueil sur l'échec sportif",
                     "Sur ce que la maladresse et la défaite révèlent du jeu.",
                     ("défaite", "perdre", "élégance", "limites")),
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
            "Racontez un objet que vous ne jetterez jamais.",
            "Faut-il dormir plus ou vivre plus ?",
            "Le meilleur conseil qu'on vous ait donné.",
            "Défendez une dépense inutile.",
            "Ce que vous feriez d'une journée de trop.",
            "La dernière fois que vous avez changé d'avis.",
        ),
        resources=(
            Resource(LIVRE, "La Vie mode d'emploi", "Georges Perec",
                     "Un immeuble, cent vies : le quotidien comme matière romanesque.",
                     ("objet", "quotidien", "habitude", "désordre")),
            Resource(LIVRE, "Tentative d'épuisement d'un lieu parisien", "Georges Perec",
                     "Trois jours à noter ce qui se passe quand il ne se passe rien.",
                     ("rien", "faire", "trajet", "observer")),
            Resource(LIVRE, "L'Usage du monde", "Nicolas Bouvier",
                     "Le voyage lent, où le trajet est tout le propos.",
                     ("trajet", "destination", "voyage", "lenteur")),
            Resource(ESSAI, "Éloge de la lenteur", "Carl Honoré",
                     "Arguments concrets pour ralentir sans culpabiliser.",
                     ("avance", "tout", "suite", "dormir", "lenteur")),
            Resource(LIVRE, "Les Choses", "Georges Perec",
                     "Un couple, ses désirs d'objets, et ce que ça dit d'une époque.",
                     ("dépense", "objet", "inutile", "jeter")),
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
            "Plaidez la cause du dernier de la classe.",
            "Faites l'éloge de la porte fermée.",
            "Expliquez le rire à une machine.",
            "Défendez le droit de se tromper en public.",
            "Improvisez le mode d'emploi d'une journée parfaite.",
            "Prononcez l'éloge de quelqu'un que vous n'aimez pas.",
        ),
        resources=(
            Resource(LIVRE, "Rhétorique", "Aristote",
                     "Le manuel fondateur : convaincre par le propos, l'orateur, l'auditoire.",
                     ("convaincre", "éloge", "plaider", "discours")),
            Resource(ESSAI, "L'Art d'avoir toujours raison", "Arthur Schopenhauer",
                     "Trente-huit stratagèmes de mauvaise foi, à reconnaître et à éviter.",
                     ("défendre", "idée", "croyez", "tromper", "raison")),
            Resource(FILM, "À voix haute : la force de la parole",
                     "Stéphane de Freitas et Ladj Ly",
                     "Des étudiants de Saint-Denis préparent un concours d'éloquence.",
                     ("parole", "éloquence", "concours", "public")),
            Resource(FILM, "Le Discours d'un roi", "Tom Hooper",
                     "Un roi bègue apprend à tenir un micro. Sur le trac, surtout.",
                     ("parole", "trac", "public", "discours")),
            Resource(LIVRE, "Exercices de style", "Raymond Queneau",
                     "Quatre-vingt-dix-neuf façons de raconter la même anecdote.",
                     ("mots", "style", "improviser", "guerre")),
        ),
    ),
)

DOMAINS_BY_KEY = {d.key: d for d in DOMAINS}


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


# --------------------------------------------------------------------------
# Tirage
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Ressources
# --------------------------------------------------------------------------

_MOT_RE = re.compile(r"[\w'’-]+", re.UNICODE)

# Mots trop fréquents pour rapprocher utilement un sujet d'une ressource.
_VIDES = {
    "faut", "il", "elle", "on", "le", "la", "les", "un", "une", "des", "de",
    "du", "au", "aux", "et", "ou", "mais", "que", "qui", "quoi", "est", "sont",
    "peut", "doit", "etre", "avoir", "a", "en", "dans", "sur", "pour", "par",
    "avec", "sans", "plus", "moins", "tres", "tout", "tous", "toute", "toutes",
    "ce", "cette", "ces", "se", "sa", "son", "ses", "nous", "vous", "ils",
    "encore", "toujours", "jamais", "vraiment", "quelque", "chose", "y",
    "ne", "pas", "si", "comme", "meme", "aussi", "deja", "vos", "votre",
}


# Les ligatures ne sont pas des accents : « œ » n'est pas décomposé par NFD.
# Sans ce repli, « cœur » et « coeur » restent deux mots distincts, et le
# rapprochement échoue selon la façon dont le sujet a été saisi.
_LIGATURES = str.maketrans({"œ": "oe", "æ": "ae", "Œ": "oe", "Æ": "ae"})


def _mots_cles(texte: str) -> set[str]:
    nfd = unicodedata.normalize("NFD", texte.lower().translate(_LIGATURES))
    sans_accent = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return {
        m for m in _MOT_RE.findall(sans_accent)
        if len(m) >= 3 and m not in _VIDES
    }


def suggest_resources(domain: Domain, topic: str, limit: int = 3) -> list[Resource]:
    """Choisit les ressources du domaine les plus proches du sujet tiré.

    Rapprochement par mots-clés, volontairement simple et déterministe. On
    aurait pu demander au modèle de choisir : il l'aurait fait mieux, mais avec
    le risque qu'il invente une référence absente de la liste. Ici, seules des
    œuvres réellement écrites à la main peuvent sortir.
    """
    if not domain.resources:
        return []

    mots = _mots_cles(topic)

    def score(r: Resource) -> tuple[int, int]:
        depuis_tags = len(mots & _mots_cles(" ".join(r.tags)))
        depuis_note = len(mots & _mots_cles(r.note + " " + r.title))
        return (depuis_tags * 2 + depuis_note, depuis_tags)

    classees = sorted(domain.resources, key=score, reverse=True)
    return classees[:limit]


def resource_payload(r: Resource) -> dict:
    return {
        "kind": r.kind,
        "title": r.title,
        "author": r.author,
        "note": r.note,
        # Lien de recherche plutôt qu'une URL directe : une adresse peut
        # mourir ou changer, une recherche sur le titre et l'auteur non.
        "search": f"{r.title} {r.author}",
    }


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
            "short": d.short,
            "level": d.level,
            "color": d.color,
            "topic_count": len(d.topics),
            "topics": list(d.topics),
        }
        for d in DOMAINS
    ]
