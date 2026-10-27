"""Shared helpers for Polish sources (ELI API, nalegalu, ...)."""

from __future__ import annotations


def normalize_act_type(native_type: str, title: str = "") -> str:
    """Map a Polish act type onto LawHub's generic act types."""
    t = native_type.lower()
    if t == "ustawa":
        return "code" if "kodeks" in title.lower() else "statute"
    if t == "rozporządzenie":
        return "regulation"
    if t == "obwieszczenie":
        # Mostly consolidated texts ("ogłoszenie jednolitego tekstu ...").
        return "consolidated_text" if "jednolitego tekstu" in title.lower() else "notice"
    if t in {"umowa międzynarodowa", "konwencja", "traktat", "protokół", "porozumienie"}:
        return "treaty"
    if t == "orzeczenie":
        return "court_ruling"
    return "other"
