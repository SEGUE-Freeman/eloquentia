"""Interface en ligne de commande.

Sert à valider le pipeline avant d'avoir la moindre interface web : c'est ici
qu'on vérifie que le retour produit est réellement utile, avant d'investir dans
la roue et les animations.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Settings
from .models import Report
from .pipeline import analyse_session
from .rubric import AXES
from .storage import HistoryStore, compute_progress, dump_json, export_curve
from .topics import draw

DEFAULT_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "transcript_demo.json"


def _setup_stdout() -> None:
    # Le terminal Windows n'est pas en UTF-8 par défaut : sans cela, les
    # accents du rapport lèvent une exception d'encodage.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _bar(score: int, width: int = 20) -> str:
    filled = int(round(score / 100 * width))
    return "#" * filled + "." * (width - filled)


def print_report(report: Report) -> None:
    m = report.metrics
    print()
    print("=" * 66)
    print(f"  {report.domain.upper()}  |  {report.topic}")
    print(f"  {report.metrics.duration_s:.0f} s sur {report.time_limit_s} s"
          f"  |  session {report.session_id}")
    print("=" * 66)

    print(f"\n  SCORE GLOBAL : {report.global_score}/100   [{_bar(report.global_score)}]\n")

    print(f"  {'aisance (mesuré)':<22} {m.fluency_score:>3}  [{_bar(m.fluency_score, 16)}]")
    for name, axis in report.analysis.axes.items():
        label = AXES[name]["label"].lower()
        print(f"  {label:<22} {axis.score:>3}  [{_bar(axis.score, 16)}]")

    print("\n  --- MESURES ---")
    print(f"  Débit          : {m.articulation_wpm:.0f} mots/min (articulation), "
          f"{m.overall_wpm:.0f} global")
    print(f"  Mots           : {m.word_count}   Phrases : {m.sentence_count} "
          f"({m.avg_sentence_words:.0f} mots/phrase)")
    print(f"  Pauses longues : {m.pauses.count_long}   "
          f"la plus longue {m.pauses.longest_s:.1f} s à {m.pauses.longest_at:.0f} s")
    print(f"  Silence        : {m.pauses.silence_ratio:.0%} du temps")
    print(f"  Tics           : {m.filler_count} ({m.filler_per_min:.1f}/min)")
    if m.fillers:
        detail = "  ".join(f"{f.pattern} x{f.count}" for f in m.fillers[:6])
        print(f"                   {detail}")
    print(f"  Richesse       : MATTR {m.mattr:.2f}   TTR {m.ttr:.2f}")
    if m.overused_words:
        print("  Sur-utilisés   : " + ", ".join(f"{w} x{c}" for w, c in m.overused_words))
    if m.prosody:
        p = m.prosody
        print(f"  Intonation     : {p.median_f0_hz:.0f} Hz, "
              f"variation {p.pitch_variation_st:.1f} demi-tons"
              f"{'  (VOIX PLATE)' if p.monotony_flag else ''}")
    else:
        print("  Intonation     : non mesurée (audio non décodable)")

    for note in m.fluency_notes:
        print(f"    - {note}")

    print("\n  --- JUGEMENT ---")
    for name, axis in report.analysis.axes.items():
        print(f"  [{axis.score:>3}] {AXES[name]['label']} : {axis.justification}")

    print("\n  --- RETOUR ---")
    print(f"  Point fort       : {report.analysis.point_fort}")
    print(f"  À corriger       : {report.analysis.axe_prioritaire}")
    print(f"  Exercice         : {report.analysis.exercice}")
    if report.analysis.reformulation:
        print(f"  Mieux dit        : {report.analysis.reformulation}")
    print(f"\n  (modèle : {report.analysis.model}, "
          f"grille v{report.analysis.rubric_version})\n")


def print_progress(progress: dict) -> None:
    print()
    if progress.get("sessions", 0) == 0:
        print("  Aucune session enregistrée.")
        return
    if "delta_vs_previous" not in progress:
        print(f"  {progress['message']}")
        print(f"  Scores : {json.dumps(progress['current'], ensure_ascii=False)}")
        return

    print(f"  {progress['sessions']} sessions (grille v{progress['rubric_version']})"
          f"  |  meilleur global : {progress['best_global']}/100")
    print(f"\n  {'axe':<14}{'actuel':>8}{'vs préc.':>10}{'vs moy. 5':>12}")
    for key, value in progress["current"].items():
        delta = progress["delta_vs_previous"].get(key, 0)
        base = progress["delta_vs_baseline"].get(key, 0.0)
        print(f"  {key:<14}{value:>8}{delta:>+10}{base:>+12.1f}")

    if progress["improving"]:
        print(f"\n  En progrès : {', '.join(progress['improving'])}")
    if progress["slipping"]:
        print(f"  En recul   : {', '.join(progress['slipping'])}")
    print()


def cmd_analyse(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    if args.mock:
        settings = Settings(
            stt_provider="mock", llm_provider="mock", data_dir=settings.data_dir
        )

    fixture = args.fixture or (DEFAULT_FIXTURE if settings.stt_provider == "mock" else None)

    report = analyse_session(
        audio_path=args.audio or "",
        domain=args.domain,
        topic=args.topic,
        time_limit_s=args.limit,
        user_id=args.user,
        settings=settings,
        fixture=fixture,
        with_prosody=not args.no_prosody,
    )

    print_report(report)

    store = HistoryStore(settings.data_dir)
    path = store.save(report)
    print(f"  Session enregistrée : {path}")

    if args.out:
        dump_json(report, args.out)
        print(f"  Rapport JSON : {args.out}")

    progress = compute_progress(store.load(args.user))
    if progress.get("sessions", 0) > 1:
        print_progress(progress)
    return 0


def cmd_tirage(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    history = HistoryStore(settings.data_dir).load(args.user)

    # On évite de retomber sur ce qui vient d'être travaillé : la surprise est
    # le ressort de l'exercice.
    recent_domains = [r.domain for r in history[-3:]]
    recent_topics = [r.topic for r in history[-15:]]

    domain, topic = draw(
        recent_domains=recent_domains,
        recent_topics=recent_topics,
        level=args.level,
    )

    print()
    print(f"  DOMAINE : {domain.label}  ({domain.level})")
    print(f"  SUJET   : {topic}")
    print(f"\n  Enregistrez-vous, puis :")
    print(f'  python -m eloquentia analyse mon_audio.wav --domain "{domain.label}" '
          f'--topic "{topic}" --user {args.user}')
    print()
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from .bench import format_result, run_bench
    from .transcription import MockTranscriber

    settings = Settings.from_env()
    transcript = MockTranscriber(args.fixture or DEFAULT_FIXTURE).transcribe("")

    modeles = args.models.split(",") if args.models else [settings.llm_model]
    print(f"\n  {args.runs} passages du même discours par modèle, température "
          f"{settings.llm_temperature}.")

    for modele in modeles:
        result = run_bench(
            transcript, args.domain, args.topic, args.limit,
            replace(settings, llm_model=modele.strip()), runs=args.runs,
        )
        print(format_result(result))
    print()
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    store = HistoryStore(settings.data_dir)
    print_progress(compute_progress(store.load(args.user)))
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    store = HistoryStore(settings.data_dir)
    history = store.load(args.user)
    if not history:
        print("\n  Aucune session enregistrée.\n")
        return 0
    print(f"\n  {'date':<20}{'global':>8}  domaine / sujet")
    for r in history:
        print(f"  {r.created_at.strftime('%Y-%m-%d %H:%M'):<20}{r.global_score:>8}  "
              f"{r.domain} / {r.topic[:40]}")
    print()
    return 0


def cmd_curve(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    store = HistoryStore(settings.data_dir)
    curve = export_curve(store.load(args.user))
    if args.out:
        dump_json(curve, args.out)
        print(f"  Courbe exportée : {args.out}")
    else:
        print(json.dumps(curve, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()

    parser = argparse.ArgumentParser(
        prog="eloquentia",
        description="Analyse de prise de parole improvisée",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyse", help="analyser un enregistrement")
    p.add_argument("audio", nargs="?", help="fichier audio (wav, mp3, m4a, webm)")
    p.add_argument("--domain", default="Société", help="domaine tiré par la roue")
    p.add_argument("--topic", required=True, help="sujet imposé")
    p.add_argument("--limit", type=int, default=120, help="temps imparti en secondes")
    p.add_argument("--user", default="anonyme")
    p.add_argument("--fixture", help="transcription rejouée (mode développement)")
    p.add_argument("--mock", action="store_true",
                   help="force la transcription et l'analyse simulées")
    p.add_argument("--no-prosody", action="store_true")
    p.add_argument("--out", help="écrire le rapport JSON dans ce fichier")
    p.set_defaults(func=cmd_analyse)

    p = sub.add_parser("tirage", help="tirer un domaine et un sujet")
    p.add_argument("--user", default="anonyme")
    p.add_argument("--level", choices=["echauffement", "standard", "exigeant"],
                   help="restreindre le tirage à un niveau")
    p.set_defaults(func=cmd_tirage)

    p = sub.add_parser("bench", help="mesurer la stabilité du jugement d'un modèle")
    p.add_argument("--runs", type=int, default=5, help="passages par modèle")
    p.add_argument("--models", help="liste séparée par des virgules")
    p.add_argument("--fixture", help="transcription à rejouer")
    p.add_argument("--domain", default="Technologie")
    p.add_argument("--topic", default="Faut-il avoir peur de l'intelligence artificielle ?")
    p.add_argument("--limit", type=int, default=120)
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("progress", help="progression d'un utilisateur")
    p.add_argument("--user", default="anonyme")
    p.set_defaults(func=cmd_progress)

    p = sub.add_parser("history", help="liste des sessions")
    p.add_argument("--user", default="anonyme")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("curve", help="export des séries pour le front")
    p.add_argument("--user", default="anonyme")
    p.add_argument("--out")
    p.set_defaults(func=cmd_curve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # message net plutôt qu'une trace brute
        print(f"\n  ERREUR : {exc}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
