"""حارس الأزرار: يعطّل تلقائياً كل زر كتابة لمن لا يملك صلاحية التعديل (Viewer).
الاستثناءات (قائمة بيضاء) فقط للتنقل والبحث والتحديث وإجراءات الحساب الشخصي."""

import functools

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from core.auth_context import get_current_role
from core.permissions import can_modify

_READONLY_HELP = "صلاحيتك للقراءة فقط."
_PATCHED_FLAG = "_smartats_readonly_patched"
_SAFE_CALLBACKS = frozenset({
    "go_to", "_step", "_set_page", "_select_job", "_clear_ask", "_go_to_reports",
    "_go_to_matching", "_go_to_jobs", "_reset_filters", "_close_drawer",
})
_SAFE_LABELS = frozenset({"🔍 بحث", "🔄 تحديث", "تسجيل الخروج", "💾 تغيير"})
_SAFE_KEY_PARTS = ("_find_", "sb_ask_clear")
_WIDGETS = ("button", "form_submit_button")


def _must_lock(label: str, kwargs: dict) -> bool:
    role = get_current_role()
    if role is None or can_modify(role):
        return False
    if getattr(kwargs.get("on_click"), "__name__", None) in _SAFE_CALLBACKS:
        return False
    key = str(kwargs.get("key") or "")
    if any(part in key for part in _SAFE_KEY_PARTS):
        return False
    return label not in _SAFE_LABELS


def _locked(kwargs: dict) -> dict:
    return {**kwargs, "disabled": True, "help": kwargs.get("help") or _READONLY_HELP}


def _patch_method(name: str) -> None:
    original = getattr(DeltaGenerator, name)

    @functools.wraps(original)
    def wrapper(self, label, *args, **kwargs):
        return original(self, label, *args, **(_locked(kwargs) if _must_lock(label, kwargs) else kwargs))

    setattr(DeltaGenerator, name, wrapper)


def _patch_module_function(name: str) -> None:
    original = getattr(st, name)

    @functools.wraps(original)
    def wrapper(label, *args, **kwargs):
        return original(label, *args, **(_locked(kwargs) if _must_lock(label, kwargs) else kwargs))

    setattr(st, name, wrapper)


def install_readonly_guard() -> None:
    """يُستدعى مرة واحدة من app.py (آمن عند إعادة الاستدعاء)."""
    if getattr(DeltaGenerator, _PATCHED_FLAG, False):
        return
    for name in _WIDGETS:
        _patch_method(name)
        _patch_module_function(name)
    setattr(DeltaGenerator, _PATCHED_FLAG, True)