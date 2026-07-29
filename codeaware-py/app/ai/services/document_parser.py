"""DocumentParserService - 文件解析（unstructured，PDF/Word/HTML/Markdown）。"""

import io

from unstructured.partition.auto import partition


class DocumentParserService:
    async def parse(self, file_content: bytes, filename: str) -> str:
        """按文件名推断 content_type，unstructured partition 为元素文本。"""
        content_type = self._guess_content_type(filename)
        elements = partition(file=io.BytesIO(file_content), content_type=content_type)
        return "\n\n".join(
            str(e.text) for e in elements if getattr(e, "text", None) and e.text.strip()
        )

    @staticmethod
    def _guess_content_type(filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return {
            "md": "text/markdown",
            "markdown": "text/markdown",
            "txt": "text/plain",
            "html": "text/html",
            "htm": "text/html",
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }.get(ext, "text/plain")
