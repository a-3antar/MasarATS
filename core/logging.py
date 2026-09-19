"""
إعداد تسجيل الأحداث (logging) المركزي للتطبيق.
يُستدعى مرة واحدة عند بدء التطبيق (من app.py).
"""

import logging
import sys

from config.settings import get_settings


def setup_logging() -> None:
    """تهيئة logging بصيغة موحّدة لكل التطبيق."""
    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    # تقليل إزعاج بعض المكتبات الخارجية الصاخبة
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """إرجاع logger باسم محدد (عادة __name__ للملف المستدعي)."""
    return logging.getLogger(name)
