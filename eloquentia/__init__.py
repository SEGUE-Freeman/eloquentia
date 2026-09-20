"""Eloquentia — pipeline d'analyse de prise de parole improvisée."""

from .config import Settings
from .models import Report, SpeechMetrics, Transcript
from .pipeline import analyse_session
from .storage import HistoryStore, compute_progress, export_curve

__all__ = [
    "Settings",
    "Report",
    "SpeechMetrics",
    "Transcript",
    "analyse_session",
    "HistoryStore",
    "compute_progress",
    "export_curve",
]

__version__ = "0.1.0"
