# Eloquentia — pipeline d'analyse de prise de parole

Moteur d'analyse pour une plateforme d'entraînement à la parole improvisée :
un sujet tiré au sort, un temps imparti, un enregistrement, et un retour
exploitable dès la prestation suivante.

Cette première étape est le **pipeline d'analyse**, volontairement construit
avant l'interface. La roue et les animations sont faciles ; ce qui décide du
succès du produit, c'est la qualité et la **stabilité** du retour.

---

## Le principe : trois couches, trois responsabilités

```
audio ─┬─> transcription horodatée ──┐
       │                             ├─> métriques déterministes ─┐
       └─> prosodie (hauteur, énergie)┘                           │
                                                                  ├─> rapport
                        sujet + métriques ─> LLM (grille figée) ──┘
```

| Couche | Qui produit | Exemples |
|---|---|---|
| Signaux audio | code (`prosody.py`) | hauteur médiane, variation d'intonation en demi-tons, monotonie |
| Signaux texte | code (`metrics.py`) | débit, pauses, tics de langage, richesse lexicale |
| Jugement | LLM (`analysis.py`) | structure, pertinence, contenu, langue, impact |

**Pourquoi cette séparation.** Un LLM à qui on demande « quel était son débit ? »
invente un chiffre plausible, et note la même prestation 62 puis 78 selon
l'humeur du tirage. Une courbe de progression construite là-dessus ne mesure
rien. Ici, tout ce qui est mesurable est mesuré par du code reproductible, et
ces mesures sont transmises au modèle **comme des faits qu'il n'a pas le droit
de re-noter**.

---

## Installation

```bash
pip install -r requirements.txt
```

`ffmpeg` est optionnel : il permet d'analyser l'intonation sur les formats
non-WAV (notamment le webm produit par les navigateurs). Sans lui, tout le
reste fonctionne, la prosodie est simplement absente du rapport.

---

## Essayer sans clé d'API

Une transcription d'exemple est fournie, avec horodatage mot à mot :

```bash
python fixtures/make_fixture.py
```

```bash
python -m eloquentia analyse --mock --topic "Faut-il avoir peur de l'IA ?" --user demo
```

Les mesures affichées sont réelles ; seul le jugement est simulé
(marqué `[simulation]`) tant qu'aucun modèle n'est configuré.

---

## Utilisation réelle

Copier `.env.example` en `.env` et renseigner les deux fournisseurs, puis :

```bash
python -m eloquentia tirage --user vous
```

```bash
python -m eloquentia analyse discours.wav --domain "Société" --topic "Le mérite existe-t-il vraiment ?" --limit 120 --user vous
```

```bash
python -m eloquentia progress --user vous
```

Autres commandes : `history` (liste des sessions), `curve --out serie.json`
(séries prêtes à tracer côté front).

---

## Ce que mesure le code

**Débit.** Deux valeurs distinctes : le débit global (mots / durée totale) et le
débit d'articulation (mots / temps de parole effectif, silences exclus). C'est
le second qui décrit la diction ; le premier décrit surtout le remplissage du
temps imparti.

**Pauses.** Les blancs entre mots sont classés : en dessous de 0,3 s c'est de
l'articulation, entre 0,6 s et 1,5 s une respiration, au-delà un trou. La plus
longue est horodatée, pour pouvoir réécouter le moment exact.

**Tics.** Hésitations pures (`euh`, `bah`…) et béquilles de discours
(`du coup`, `en fait`, `voilà`…), les expressions multi-mots étant comptées une
seule fois. Le taux par minute compte davantage que le total brut.

**Richesse lexicale.** Le MATTR (type-token ratio à fenêtre glissante) plutôt
que le TTR brut : le TTR chute mécaniquement quand le discours s'allonge, et un
discours de 3 minutes paraîtrait plus pauvre qu'un de 1 minute. Ce biais
afficherait une fausse régression sur la courbe.

**Intonation.** Fréquence fondamentale par autocorrélation, variation exprimée
en demi-tons — comparable d'une voix grave à une voix aiguë, contrairement à un
écart-type en hertz. En dessous de 2 demi-tons de variation, la voix est plate.

**Score d'aisance.** Combinaison pondérée de ces mesures par une formule figée
(`metrics.compute_fluency`). Les tics y pèsent le plus lourd : c'est le défaut
le plus audible et le plus corrigeable chez un orateur qui débute.

---

## Ce que juge le LLM

Cinq axes seulement — structure, pertinence, contenu, langue, impact — notés
selon une grille à descripteurs explicites (`rubric.py`), à température 0.

Le retour est délibérément réduit à **un point fort, un axe prioritaire, un
exercice**. Un orateur qui reçoit dix reproches n'en corrige aucun.

La grille est versionnée (`RUBRIC_VERSION`). Toute modification change
l'échelle : les scores d'une version ne sont jamais comparés à ceux d'une
autre, `compute_progress` filtre là-dessus. Ce garde-fou évite d'annoncer un
progrès qui n'est qu'un changement de règle.

---

## Tests

```bash
python -m pytest tests/ -q
```

Les tests de prosodie valident le détecteur sur des signaux synthétiques dont
la hauteur est connue par construction : il doit retrouver 130 Hz à 3 % près,
signaler une voix plate et ne pas signaler une intonation variée.

---

## Limites connues

- **Ancrages à recalibrer.** Les seuils de débit et les paliers du score
  d'aisance viennent de valeurs de référence sur le français parlé, pas de
  mesures sur de vrais utilisateurs de la plateforme. Sur la transcription
  d'exemple, une prestation propre atteint déjà 98/100 : le haut de l'échelle
  est trop accessible. À recalibrer sur une vingtaine d'enregistrements réels,
  idéalement notés en parallèle par un humain.
- **Timestamps de la fixture synthétiques.** Ils imitent un rythme plausible
  mais lissent les micro-hésitations d'une vraie voix. Les métriques calculées
  dessus sont donc optimistes.
- **Détection de F0 volontairement simple.** L'autocorrélation confond parfois
  une octave ; l'effet est absorbé par la médiane et le rognage des extrêmes,
  suffisant pour une tendance d'intonation, insuffisant pour de la phonétique.
- **Exactitude factuelle non vérifiée.** Le modèle est invité à signaler les
  erreurs de culture générale, mais il peut lui-même se tromper. Ne pas
  présenter ce retour comme une vérification de faits.
- **Qualité du français du modèle.** Beaucoup de modèles ouverts sont médiocres
  en français. C'est le premier critère de choix, avant le prix et la vitesse.

---

## Avant la mise en ligne

La plateforme visée est multi-utilisateurs et hébergée : elle stockera des
**enregistrements de voix**, qui sont des données personnelles. À traiter avant
l'ouverture au public, pas après :

- consentement explicite avant le premier enregistrement ;
- durée de rétention annoncée, et suppression effective de l'audio à l'échéance ;
- suppression de compte qui efface réellement les fichiers audio ;
- information claire sur le fournisseur tiers qui reçoit l'audio et le texte.

Le stockage actuel (JSON Lines par utilisateur) est un substitut de
développement. `storage.py` n'expose que quatre fonctions : le remplacement par
une base de données ne touchera pas au reste du code.
