"""دوال مساعدة مشتركة بين الصفحات (بدل تكرارها في كل view). لا CSS هنا ولا استعلامات."""

import re
from collections.abc import Callable

import streamlit as st

from core.exceptions import SmartATSError
from database.database import get_db_session

_STATUS_PREFIX_CHARS = "✓✔⚠❌\ufe0f "

# (اسم الوحدة داخل views، اسم دالة مسح الكاش) - أضف هنا أي صفحة جديدة لها كاش.
# ملاحظة: دوال المسح هنا يجب ألا تستدعي invalidate_all (تفادياً للتكرار اللانهائي).
_CACHE_CLEARERS: tuple[tuple[str, str], ...] = (
    ("jobs", "_invalidate_job_related_caches"),
    ("candidates", "invalidate_cache"),
    ("dashboard", "clear_cache"),
    ("organization", "_invalidate"),
    ("job_candidates", "clear_cache"),
    ("pipeline", "clear_cache"),
)


def clean_line(text: str) -> str:
    """يزيل رموز ✓ ⚠ ❌ من بداية سطر نقطة قوة/فجوة."""
    return (text or "").lstrip(_STATUS_PREFIX_CHARS).strip()


def split_items(raw: str) -> list[str]:
    """تقسيم نص مفصول بفاصلة (إنجليزية أو عربية) أو أسطر إلى قائمة نظيفة."""
    return [part.strip() for part in re.split(r"[,،\n]", raw or "") if part.strip()]


def invalidate_all() -> None:
    """يمسح كاش كل الصفحات بعد أي كتابة. فشل مسح صفحة لا يوقف العملية."""
    import importlib

    for module_name, fn_name in _CACHE_CLEARERS:
        try:
            module = importlib.import_module(f"views.{module_name}")
            getattr(module, fn_name)()
        except Exception:  # noqa: BLE001
            pass


def run_action(action: Callable, success: str | None = None, rerun: bool = True) -> bool:
    """
    ينفّذ عملية كتابة داخل جلسة قاعدة بيانات.
    عند الخطأ: يعرض رسالته. عند النجاح: يمسح الكاش، يعرض toast (إن وُجدت رسالة)، ويعيد التشغيل.
    """
    try:
        with get_db_session() as session:
            action(session)
    except SmartATSError as exc:
        st.error(str(exc))
        return False
    invalidate_all()
    if success:
        st.toast(success)
    if rerun:
        st.rerun()
    return True
