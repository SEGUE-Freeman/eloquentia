/* Eloquentia — logique de l'interface.
   Aucune dépendance : le pipeline vit côté serveur, le navigateur ne fait que
   tirer, chronométrer, enregistrer et afficher. */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// Identité locale, en attendant les comptes. Le serveur range l'historique
// sous cette clé.
const UTILISATEUR = localStorage.getItem("eloquentia-user") || "moi";

const etat = {
  domaines: [],
  tirage: null,
  dureeS: 120,
  enregistreur: null,
  morceaux: [],
  flux: null,
  minuterie: null,
  restant: 0,
  audioCtx: null,
  animLevel: null,
};

/* ───────────────────────────── Navigation ───────────────────────────── */

function aller(nom) {
  $$(".ecran").forEach((e) => e.classList.remove("actif"));
  $(`#ecran-${nom}`).classList.add("actif");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (nom === "progres") chargerProgression();
}

$$("[data-aller]").forEach((b) => b.addEventListener("click", () => aller(b.dataset.aller)));

$$(".replier").forEach((b) =>
  b.addEventListener("click", () => {
    const cible = $(`#${b.dataset.cible}`);
    cible.hidden = !cible.hidden;
    b.textContent = cible.hidden ? "Voir la transcription" : "Masquer la transcription";
  })
);

/* ───────────────────────────── La roue ───────────────────────────── */

const RAYON = 190;
const CENTRE = 200;

function cheminSecteur(i, n) {
  const pas = (2 * Math.PI) / n;
  // On part du haut (midi), là où se trouve le pointeur.
  const a0 = i * pas - Math.PI / 2;
  const a1 = a0 + pas;
  const x0 = CENTRE + RAYON * Math.cos(a0);
  const y0 = CENTRE + RAYON * Math.sin(a0);
  const x1 = CENTRE + RAYON * Math.cos(a1);
  const y1 = CENTRE + RAYON * Math.sin(a1);
  return `M${CENTRE},${CENTRE} L${x0.toFixed(2)},${y0.toFixed(2)} ` +
         `A${RAYON},${RAYON} 0 0,1 ${x1.toFixed(2)},${y1.toFixed(2)} Z`;
}

function construireRoue(domaines) {
  const g = $("#secteurs");
  const n = domaines.length;
  const pasDeg = 360 / n;
  g.innerHTML = "";

  domaines.forEach((d, i) => {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", cheminSecteur(i, n));
    path.setAttribute("fill", d.color);
    path.setAttribute("class", "secteur");
    g.appendChild(path);

    // Libellé posé le long du rayon, pas en travers : un texte tangentiel
    // déborde sur les secteurs voisins dès qu'il dépasse quelques lettres.
    const centreDeg = (i + 0.5) * pasDeg;
    const theta = ((centreDeg - 90) * Math.PI) / 180;
    const rTexte = 122;
    const x = CENTRE + rTexte * Math.cos(theta);
    const y = CENTRE + rTexte * Math.sin(theta);
    // Au-delà d'un demi-tour, le texte se retrouverait la tête en bas.
    const rotation = centreDeg > 180 ? centreDeg + 90 : centreDeg - 90;

    const texte = document.createElementNS("http://www.w3.org/2000/svg", "text");
    texte.setAttribute("transform", `translate(${x.toFixed(2)},${y.toFixed(2)}) rotate(${rotation.toFixed(2)})`);
    texte.setAttribute("text-anchor", "middle");
    texte.setAttribute("dominant-baseline", "middle");
    texte.setAttribute("class", "secteur-texte");
    texte.textContent = d.short || d.label;
    g.appendChild(texte);
  });
}

/* Le domaine est tiré par le SERVEUR, qui seul connaît l'historique.
   L'animation ne décide de rien : elle va chercher le secteur déjà choisi.
   C'est ce qui garantit que le sujet annoncé est bien celui qui sera
   enregistré avec la session. */
function tournerVers(indice, n) {
  const pasDeg = 360 / n;
  const centreDeg = (indice + 0.5) * pasDeg;
  // Décalage aléatoire à l'intérieur du secteur : sans lui, la roue
  // s'arrête toujours pile au même endroit et l'illusion tombe.
  const jitter = (Math.random() - 0.5) * pasDeg * 0.6;
  const tours = 5 + Math.floor(Math.random() * 3);
  const angle = tours * 360 - centreDeg + jitter;
  $("#secteurs").style.transform = `rotate(${angle}deg)`;
  return angle;
}

async function lancerRoue() {
  const bouton = $("#btn-tourner");
  if (bouton.disabled) return;
  bouton.disabled = true;
  $("#annonce-domaine").textContent = "";

  etat.dureeS = parseInt($("#duree").value, 10);

  let tirage;
  try {
    const corps = new FormData();
    corps.append("user", UTILISATEUR);
    corps.append("level", $("#niveau").value);
    const r = await fetch("/api/draw", { method: "POST", body: corps });
    if (!r.ok) throw new Error(await r.text());
    tirage = await r.json();
  } catch (e) {
    $("#annonce-domaine").textContent = "Le tirage a échoué. Le serveur répond-il ?";
    bouton.disabled = false;
    return;
  }

  etat.tirage = tirage;
  const indice = etat.domaines.findIndex((d) => d.key === tirage.domain_key);
  tournerVers(indice, etat.domaines.length);

  const reduit = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const attente = reduit ? 1000 : 5100;

  setTimeout(() => {
    $("#annonce-domaine").textContent = tirage.domain;
    revelerSujet(tirage);
    bouton.disabled = false;
  }, attente);
}

/* Deuxième tirage : le sujet à l'intérieur du domaine. Le défilement rapide
   rend visible ce second hasard, que l'utilisateur ne verrait pas sinon. */
function revelerSujet(tirage) {
  aller("parole");
  $("#parole-domaine").textContent = tirage.domain;
  preparerChrono(etat.dureeS);

  const domaine = etat.domaines.find((d) => d.key === tirage.domain_key);
  const candidats = (domaine && domaine.topics) || [tirage.topic];
  const cible = $("#parole-sujet");

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || candidats.length < 2) {
    cible.textContent = tirage.topic;
    return;
  }

  let tours = 0;
  const total = 14;
  const defilement = setInterval(() => {
    cible.textContent = candidats[Math.floor(Math.random() * candidats.length)];
    cible.style.opacity = 0.45;
    if (++tours >= total) {
      clearInterval(defilement);
      cible.textContent = tirage.topic;
      cible.style.opacity = 1;
    }
  }, 75);
}

$("#btn-tourner").addEventListener("click", lancerRoue);

/* ───────────────────────────── Chronomètre ───────────────────────────── */

const CIRCONFERENCE = 2 * Math.PI * 96;

function formaterTemps(s) {
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function preparerChrono(dureeS) {
  etat.restant = dureeS;
  $("#chrono-texte").textContent = formaterTemps(dureeS);
  $("#chrono-etat").textContent = "prêt";
  $("#chrono-etat").classList.remove("enregistre");
  const arc = $("#chrono-arc");
  arc.style.strokeDasharray = CIRCONFERENCE;
  arc.style.strokeDashoffset = 0;
  arc.classList.remove("tiede", "chaud");
  $("#btn-demarrer").hidden = false;
  $("#btn-arreter").hidden = true;
  $("#parole-erreur").textContent = "";
  $("#niveau-micro span").style.width = "0%";
}

function tictac() {
  etat.restant -= 1;
  $("#chrono-texte").textContent = formaterTemps(Math.max(0, etat.restant));

  const ecoule = 1 - etat.restant / etat.dureeS;
  const arc = $("#chrono-arc");
  arc.style.strokeDashoffset = CIRCONFERENCE * ecoule;

  const reste = etat.restant / etat.dureeS;
  arc.classList.toggle("tiede", reste <= 0.4 && reste > 0.15);
  arc.classList.toggle("chaud", reste <= 0.15);

  if (etat.restant <= 0) arreter();
}

/* ───────────────────────────── Enregistrement ───────────────────────────── */

function suivreNiveau(flux) {
  try {
    etat.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = etat.audioCtx.createMediaStreamSource(flux);
    const analyseur = etat.audioCtx.createAnalyser();
    analyseur.fftSize = 512;
    source.connect(analyseur);
    const donnees = new Uint8Array(analyseur.frequencyBinCount);
    const barre = $("#niveau-micro span");

    const boucle = () => {
      analyseur.getByteTimeDomainData(donnees);
      let somme = 0;
      for (const v of donnees) somme += (v - 128) ** 2;
      const rms = Math.sqrt(somme / donnees.length) / 128;
      barre.style.width = `${Math.min(100, rms * 260)}%`;
      etat.animLevel = requestAnimationFrame(boucle);
    };
    boucle();
  } catch {
    /* Le vumètre est un confort : son échec ne doit pas empêcher d'enregistrer. */
  }
}

async function demarrer() {
  $("#parole-erreur").textContent = "";
  let flux;
  try {
    flux = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
  } catch (e) {
    $("#parole-erreur").textContent =
      "Micro inaccessible. Autorise l'accès dans la barre d'adresse, puis réessaie.";
    return;
  }

  etat.flux = flux;
  etat.morceaux = [];

  const type = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : "";
  etat.enregistreur = new MediaRecorder(flux, type ? { mimeType: type } : {});
  etat.enregistreur.ondataavailable = (e) => e.data.size && etat.morceaux.push(e.data);
  etat.enregistreur.onstop = envoyer;
  etat.enregistreur.start();

  suivreNiveau(flux);

  $("#chrono-etat").textContent = "enregistrement";
  $("#chrono-etat").classList.add("enregistre");
  $("#btn-demarrer").hidden = true;
  $("#btn-arreter").hidden = false;
  etat.minuterie = setInterval(tictac, 1000);
}

function libererMicro() {
  clearInterval(etat.minuterie);
  if (etat.animLevel) cancelAnimationFrame(etat.animLevel);
  if (etat.audioCtx) etat.audioCtx.close().catch(() => {});
  etat.audioCtx = null;
  // Couper les pistes éteint le voyant du micro : ne jamais laisser un
  // enregistrement ouvert après la fin de l'exercice.
  if (etat.flux) etat.flux.getTracks().forEach((t) => t.stop());
  etat.flux = null;
}

function arreter() {
  if (!etat.enregistreur || etat.enregistreur.state === "inactive") return;
  etat.enregistreur.stop();
  libererMicro();
}

function abandonner() {
  if (etat.enregistreur && etat.enregistreur.state !== "inactive") {
    etat.enregistreur.onstop = null;
    etat.enregistreur.stop();
  }
  libererMicro();
  aller("roue");
}

$("#btn-demarrer").addEventListener("click", demarrer);
$("#btn-arreter").addEventListener("click", arreter);
$("#btn-abandon").addEventListener("click", abandonner);

/* ───────────────────────────── Envoi et analyse ───────────────────────────── */

const ETAPES = [
  "Transcription de l'enregistrement…",
  "Mesure du débit et des pauses…",
  "Analyse de l'intonation…",
  "Lecture du discours par le modèle…",
];

async function envoyer() {
  const blob = new Blob(etat.morceaux, { type: "audio/webm" });
  if (blob.size < 2048) {
    $("#parole-erreur").textContent = "Rien n'a été capté. Vérifie ton micro.";
    preparerChrono(etat.dureeS);
    return;
  }

  aller("attente");
  let i = 0;
  $("#attente-etape").textContent = ETAPES[0];
  const rotation = setInterval(() => {
    i = (i + 1) % ETAPES.length;
    $("#attente-etape").textContent = ETAPES[i];
  }, 4000);

  const corps = new FormData();
  corps.append("audio", blob, "discours.webm");
  // On renvoie la référence du sujet, jamais son texte : le serveur le
  // résout lui-même, ce qui rend impossible toute divergence entre le sujet
  // tiré et celui enregistré avec la session.
  corps.append("domain_key", etat.tirage.domain_key);
  corps.append("topic_index", etat.tirage.topic_index);
  corps.append("time_limit_s", etat.dureeS);
  corps.append("user", UTILISATEUR);

  try {
    const r = await fetch("/api/sessions", { method: "POST", body: corps });
    const donnees = await r.json();
    if (!r.ok) throw new Error(donnees.detail || "Analyse impossible");
    afficherResultat(donnees);
  } catch (e) {
    aller("parole");
    $("#parole-erreur").textContent = e.message;
    preparerChrono(etat.dureeS);
  } finally {
    clearInterval(rotation);
  }
}

/* ───────────────────────────── Résultat ───────────────────────────── */

const LIBELLES = {
  structure: "Structure",
  pertinence: "Pertinence",
  contenu: "Contenu",
  langue: "Langue",
  impact: "Impact",
};

function afficherResultat(rapport) {
  aller("resultat");
  const m = rapport.metrics;

  $("#res-sujet").innerHTML =
    `<span class="etq-dom">${echapper(rapport.domain)}</span>${echapper(rapport.topic)}`;
  $("#res-global").textContent = rapport.global_score;

  const anneau = $("#anneau-arc");
  const circ = 2 * Math.PI * 86;
  anneau.style.strokeDasharray = circ;
  anneau.style.strokeDashoffset = circ;
  requestAnimationFrame(() =>
    setTimeout(() => {
      anneau.style.strokeDashoffset = circ * (1 - rapport.global_score / 100);
    }, 120)
  );

  // Axes : l'aisance vient du code, les cinq autres du modèle. La distinction
  // est visible (couleur et mention), parce qu'elle change ce que vaut la note.
  const axes = $("#res-axes");
  axes.innerHTML = "";
  ajouterAxe(axes, "Aisance", m.fluency_score, true, "");
  for (const [cle, axe] of Object.entries(rapport.analysis.axes)) {
    ajouterAxe(axes, LIBELLES[cle] || cle, axe.score, false, axe.justification);
  }

  const pct = Math.round(m.time_usage_ratio * 100);
  const tuiles = [
    [`${m.articulation_wpm.toFixed(0)}`, "mots / minute", m.articulation_wpm > 190 || m.articulation_wpm < 115],
    [`${m.filler_count}`, "tics de langage", m.filler_per_min >= 4],
    [`${m.pauses.count_long}`, "silences longs", m.pauses.count_long >= 3],
    [`${pct}%`, "du temps utilisé", pct < 70],
    [`${m.word_count}`, "mots prononcés", false],
    [
      m.prosody ? `${m.prosody.pitch_variation_st.toFixed(1)}` : "—",
      m.prosody ? "demi-tons d'écart" : "intonation non mesurée",
      m.prosody ? m.prosody.monotony_flag : false,
    ],
  ];
  $("#res-mesures").innerHTML = tuiles
    .map(([v, l, alerte]) =>
      `<div class="mesure-tuile${alerte ? " alerte" : ""}"><b>${v}</b><span>${l}</span></div>`
    )
    .join("");

  $("#res-notes").innerHTML = m.fluency_notes.map((n) => `<li>${echapper(n)}</li>`).join("");

  const a = rapport.analysis;
  $("#res-retour").innerHTML = [
    ["fort", "Point fort", a.point_fort],
    ["corriger", "À corriger en priorité", a.axe_prioritaire],
    ["exercice", "Pour la prochaine fois", a.exercice],
    a.reformulation ? ["mieux", "Mieux dit", a.reformulation] : null,
  ]
    .filter(Boolean)
    .map(
      ([classe, titre, texte]) =>
        `<div class="retour-carte ${classe}"><h4>${titre}</h4><p>${echapper(texte)}</p></div>`
    )
    .join("");

  $("#res-transcription").textContent = rapport.transcript.text;
  $("#res-transcription").hidden = true;

  const audio = $("#res-audio");
  if (rapport.audio_path) {
    audio.src = `/api/audio/${rapport.audio_path}`;
    audio.hidden = false;
  } else {
    audio.hidden = true;
  }
}

function ajouterAxe(parent, nom, valeur, estCode, justification) {
  const ligne = document.createElement("div");
  ligne.className = "axe-ligne";
  ligne.innerHTML =
    `<div class="axe-nom">${nom}${estCode ? '<span class="mesure">mesuré</span>' : ""}</div>` +
    `<div class="axe-piste"><div class="axe-barre${estCode ? " code" : ""}"></div></div>` +
    `<div class="axe-valeur">${valeur}</div>` +
    (justification ? `<p class="axe-just">${echapper(justification)}</p>` : "");
  parent.appendChild(ligne);
  requestAnimationFrame(() =>
    setTimeout(() => {
      ligne.querySelector(".axe-barre").style.width = `${valeur}%`;
    }, 200)
  );
}

function echapper(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

/* ───────────────────────────── Progression ───────────────────────────── */

async function chargerProgression() {
  const resume = $("#progres-resume");
  try {
    const r = await fetch(`/api/history/${encodeURIComponent(UTILISATEUR)}`);
    const d = await r.json();

    if (!d.total) {
      resume.textContent = "Aucune session pour l'instant. Lance la roue.";
      $("#progres-courbe").innerHTML = "";
      $("#progres-table").innerHTML = "";
      return;
    }

    const p = d.progression;
    resume.textContent =
      `${d.total} session${d.total > 1 ? "s" : ""} · ${d.domaines_travailles.length} domaine` +
      `${d.domaines_travailles.length > 1 ? "s" : ""} travaillé` +
      `${d.domaines_travailles.length > 1 ? "s" : ""}` +
      (p.best_global ? ` · meilleur score ${p.best_global}/100` : "");

    dessinerCourbe(d.courbe);
    dessinerTable(p);
  } catch {
    resume.textContent = "Impossible de charger l'historique.";
  }
}

function dessinerCourbe(tous) {
  const zone = $("#progres-courbe");

  // Une note obtenue avec une grille antérieure ne se compare pas aux
  // suivantes : la tracer sur la même courbe afficherait une marche qui n'est
  // pas un progrès. On ne garde que la version en cours.
  const version = tous.length ? tous[tous.length - 1].rubric_version : null;
  const points = tous.filter((p) => p.rubric_version === version);
  const ecartees = tous.length - points.length;

  const mention = ecartees
    ? `<p class="note-discrete">${ecartees} session${ecartees > 1 ? "s" : ""} ` +
      `notée${ecartees > 1 ? "s" : ""} avec une grille antérieure ne ` +
      `${ecartees > 1 ? "figurent" : "figure"} pas sur la courbe.</p>`
    : "";

  if (points.length < 2) {
    zone.innerHTML =
      '<p class="note-discrete">Il faut au moins deux sessions notées avec la ' +
      "grille actuelle pour tracer une courbe.</p>" + mention;
    return;
  }

  const L = 600, H = 200, marge = 26;
  const x = (i) => marge + (i * (L - 2 * marge)) / (points.length - 1);
  const y = (v) => H - marge - (v / 100) * (H - 2 * marge);

  const ligne = points.map((p, i) => `${x(i).toFixed(1)},${y(p.global).toFixed(1)}`).join(" ");
  const grille = [0, 25, 50, 75, 100]
    .map(
      (v) =>
        `<line class="courbe-grille" x1="${marge}" y1="${y(v)}" x2="${L - marge}" y2="${y(v)}"/>` +
        `<text class="courbe-legende" x="4" y="${y(v) + 3}">${v}</text>`
    )
    .join("");
  const pts = points
    .map((p, i) => `<circle class="courbe-point" cx="${x(i).toFixed(1)}" cy="${y(p.global).toFixed(1)}" r="3.5"/>`)
    .join("");

  zone.innerHTML =
    `<svg viewBox="0 0 ${L} ${H}">${grille}` +
    `<polyline class="courbe-ligne" points="${ligne}"/>${pts}</svg>` + mention;
}

function dessinerTable(p) {
  const table = $("#progres-table");
  if (!p.current) {
    table.innerHTML = "";
    return;
  }
  if (!p.delta_vs_previous) {
    table.innerHTML = `<p class="note-discrete">${echapper(p.message || "")}</p>`;
    return;
  }

  table.innerHTML = Object.entries(p.current)
    .map(([cle, val]) => {
      const d = p.delta_vs_previous[cle] ?? 0;
      const classe = d > 0 ? "hausse" : d < 0 ? "baisse" : "stable";
      const signe = d > 0 ? `+${d}` : d < 0 ? `${d}` : "—";
      return (
        `<div class="progres-ligne"><span class="nom">${LIBELLES[cle] || cle}</span>` +
        `<span class="val">${val}</span><span class="delta ${classe}">${signe}</span></div>`
      );
    })
    .join("");
}

/* ───────────────────────────── Démarrage ───────────────────────────── */

(async function init() {
  try {
    const r = await fetch("/api/domains");
    etat.domaines = await r.json();
    construireRoue(etat.domaines);
  } catch {
    $("#annonce-domaine").textContent = "Le serveur ne répond pas.";
  }
})();
