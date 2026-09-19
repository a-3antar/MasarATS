"""استخلاص النص والصورة من ملفات Word (.docx) باستخدام python-docx."""

import io

from core.exceptions import DocumentParsingError
from core.logging import get_logger
from document_processing.base import DocumentParser, PhotoCandidate, pick_best_photo

logger = get_logger(__name__)


class WordParser(DocumentParser):
    """يستخلص النص من ملفات .docx (الفقرات والجداول)."""

    def extract_text(self, file_path: str) -> str:
        try:
            import docx
        except ImportError as exc:
            raise DocumentParsingError("مكتبة python-docx غير مثبّتة (pip install python-docx).") from exc

        try:
            document = docx.Document(file_path)
            parts: list[str] = [p.text for p in document.paragraphs if p.text.strip()]

            for table in document.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells)
                    if row_text.strip(" |"):
                        parts.append(row_text)

            text = "\n".join(parts).strip()
            if not text:
                raise DocumentParsingError("الملف لا يحتوي على نص قابل للاستخلاص.")
            return text
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"فشل تحليل ملف Word: {exc}") from exc

    def extract_photo(self, file_path: str) -> tuple[bytes, str] | None:
        """يبحث عن أنسب صورة شخصية في متن الملف وفي الـ header (كثير من القوالب تضعها هناك)."""
        try:
            import docx
            from PIL import Image
        except ImportError:
            return None

        try:
            document = docx.Document(file_path)
            parts = [document.part]
            for section in document.sections:
                if not section.header.is_linked_to_previous:
                    parts.append(section.header.part)

            found: list[PhotoCandidate] = []
            seen_parts: set[str] = set()
            for part in parts:
                for rel in part.rels.values():
                    if rel.is_external or "image" not in rel.reltype:
                        continue
                    partname = str(rel.target_part.partname)
                    if partname in seen_parts:
                        continue
                    seen_parts.add(partname)

                    blob = rel.target_part.blob
                    try:
                        with Image.open(io.BytesIO(blob)) as image:
                            found.append((blob, (image.format or "png").lower(), image.width, image.height))
                    except Exception:  # noqa: BLE001 - صيغ مثل EMF/WMF لا يقرؤها Pillow؛ نتجاهلها
                        continue
            return pick_best_photo(found)
        except Exception as exc:
            logger.warning("Photo extraction from DOCX failed: %s", exc)
            return None