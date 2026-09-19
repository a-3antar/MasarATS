"""
دوال أمان أساسية.

ملاحظة: هذه المرحلة تركّز فقط على تجزئة (hashing) كلمات المرور — وهي ممارسة
أساسية لا تُعتبر "تشفير بيانات" بالمعنى الذي تم تأجيله (تشفير ملفات
السير الذاتية والبيانات المخزّنة). لا يجوز تخزين كلمات المرور كنص صريح
بأي حال، لذا هذا الجزء غير مؤجل.
"""

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """تحويل كلمة المرور إلى hash آمن للتخزين في قاعدة البيانات."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """التحقق من تطابق كلمة مرور مُدخلة مع الـ hash المخزّن."""
    return _pwd_context.verify(plain_password, hashed_password)
