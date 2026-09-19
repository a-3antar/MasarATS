"""
استثناءات مخصصة للتطبيق.
تُستخدم بدل الاستثناءات العامة لتوضيح سبب الخطأ والسماح بمعالجته بشكل مناسب في كل طبقة.
"""


class SmartATSError(Exception):
    """الاستثناء الأساسي الذي ترث منه كل استثناءات التطبيق."""


class ValidationError(SmartATSError):
    """بيانات غير صالحة (فشل تحقق Pydantic أو تحقق منطق العمل)."""


class DatabaseError(SmartATSError):
    """خطأ أثناء التعامل مع قاعدة البيانات."""


class ConfigurationError(SmartATSError):
    """إعداد ناقص أو غير صحيح (مثل مفتاح API مفقود)."""


# --- أخطاء المصادقة (Authentication) ---

class AuthenticationError(SmartATSError):
    """فشل تسجيل الدخول (اسم مستخدم أو كلمة مرور غير صحيحة)."""


class UserAlreadyExistsError(SmartATSError):
    """محاولة تسجيل مستخدم باسم مستخدم أو بريد إلكتروني مستخدم مسبقاً."""


class InactiveUserError(SmartATSError):
    """المستخدم موجود لكن حسابه معطّل."""


# --- أخطاء ستُستخدم في المراحل القادمة (معالجة المستندات وAI) ---

class UnsupportedFileTypeError(SmartATSError):
    """نوع الملف المرفوع غير مدعوم."""


class DocumentParsingError(SmartATSError):
    """فشل استخلاص النص من المستند."""


class AIServiceError(SmartATSError):
    """خطأ أثناء الاتصال بخدمة الذكاء الاصطناعي أو معالجة استجابتها."""


class DuplicateCandidateError(SmartATSError):
    """تم اكتشاف مرشح مكرر محتمل."""
