"""إرسال البريد الإلكتروني عبر SMTP (مستخدم حالياً لكود استعادة كلمة المرور)."""

import smtplib
import ssl
from email.message import EmailMessage

from config.settings import get_settings
from core.exceptions import ConfigurationError
from core.logging import get_logger

logger = get_logger(__name__)
_SMTP_TIMEOUT_SECONDS = 20
_SSL_PORT = 465


class EmailService:
    @staticmethod
    def send(to_address: str, subject: str, body: str) -> None:
        """يرسل رسالة نصية. يرفع ConfigurationError إن لم يُضبط SMTP أو فشل الإرسال."""
        settings = get_settings()
        if not settings.email_enabled:
            raise ConfigurationError("خدمة البريد غير مضبوطة. تواصل مع مسؤول النظام.")

        message = EmailMessage()
        message["From"] = settings.smtp_from or settings.smtp_user
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body)

        try:
            if settings.smtp_port == _SSL_PORT:
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=_SMTP_TIMEOUT_SECONDS,
                                      context=ssl.create_default_context()) as server:
                    EmailService._login(server, settings)
                    server.send_message(message)
            else:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=_SMTP_TIMEOUT_SECONDS) as server:
                    if settings.smtp_use_tls:
                        server.starttls(context=ssl.create_default_context())
                    EmailService._login(server, settings)
                    server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("Failed to send email: %s", exc)
            raise ConfigurationError("تعذّر إرسال البريد. تحقق من إعدادات SMTP.") from exc

    @staticmethod
    def _login(server, settings) -> None:
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)