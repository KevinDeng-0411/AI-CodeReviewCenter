"""DocumentParserService - C1-C 有界上传所用的确定性文本解析。

Markdown/TXT/HTML/DOCX 继续使用 unstructured；PDF 仅用 pypdf 提取文本层，
不启用 OCR、视觉模型或后台 Worker。未知扩展名不再静默降级为纯文本。
"""

import io

import anyio
from pypdf import PdfReader
from unstructured.partition.auto import partition


class DocumentParserService:
    PARTITION_CONTENT_TYPES: dict[str, str] = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".html": "text/html",
        ".htm": "text/html",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    SUPPORTED_MIME_TYPES: dict[str, frozenset[str]] = {
        ".txt": frozenset({"text/plain"}),
        ".md": frozenset({"text/markdown", "text/plain"}),
        ".markdown": frozenset({"text/markdown", "text/plain"}),
        ".html": frozenset({"text/html"}),
        ".htm": frozenset({"text/html"}),
        ".pdf": frozenset({"application/pdf"}),
        ".docx": frozenset(
            {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
        ),
    }
    GENERIC_MIME_TYPES = frozenset({"", "application/octet-stream"})

    async def parse(self, file_content: bytes, filename: str) -> str:
        """在线程中解析文件；请求仍等待结果，不引入异步索引 Worker。"""
        return await anyio.to_thread.run_sync(self._parse_sync, file_content, filename)

    @classmethod
    def supports_upload(cls, filename: str, content_type: str | None) -> bool:
        """扩展名必须受支持；MIME 必须匹配或为浏览器通用二进制类型。"""
        ext = cls.extension(filename)
        allowed = cls.SUPPORTED_MIME_TYPES.get(ext)
        if allowed is None:
            return False
        normalized_mime = (content_type or "").split(";", 1)[0].strip().lower()
        return normalized_mime in allowed or normalized_mime in cls.GENERIC_MIME_TYPES

    @staticmethod
    def safe_filename(filename: str | None) -> str:
        """丢弃客户端可能提交的 POSIX/Windows 路径，只保留文件名。"""
        return (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()

    @staticmethod
    def extension(filename: str) -> str:
        name = filename.lower()
        return f".{name.rsplit('.', 1)[-1]}" if "." in name else ""

    def _parse_sync(self, file_content: bytes, filename: str) -> str:
        ext = self.extension(filename)
        if ext == ".pdf":
            reader = PdfReader(io.BytesIO(file_content))
            return "\n\n".join(text for page in reader.pages if (text := page.extract_text()))

        content_type = self._guess_content_type(filename)
        elements = partition(file=io.BytesIO(file_content), content_type=content_type)
        return "\n\n".join(
            str(e.text) for e in elements if getattr(e, "text", None) and e.text.strip()
        )

    @classmethod
    def _guess_content_type(cls, filename: str) -> str:
        ext = cls.extension(filename)
        allowed = cls.SUPPORTED_MIME_TYPES.get(ext)
        if allowed is None:
            raise ValueError("unsupported document type")
        return cls.PARTITION_CONTENT_TYPES[ext]
