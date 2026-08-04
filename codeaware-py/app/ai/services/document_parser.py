"""DocumentParserService - 有界上传所用的确定性文本解析（C5 元素感知）。

Markdown/TXT/HTML/DOCX 经 unstructured partition 解析为带语义标签的 Elements，再按
类型感知序列化（Title->`#`、ListItem->`-`），使 chunk_by_title 的章节感知对 DOCX/HTML
也生效（不再退化为定长滑窗）。PDF 用 pypdf 做文本层探针：无文本层（扫描版）返回 ""，
由路由层显式拒绝；有文本层则走 pdfminer 布局分析（字号标题检测）。不走
unstructured.partition.pdf——它无条件 import unstructured_inference（拖 torch/opencv
视觉模型栈），违反 C5“不引视觉模型”约束。不启用 OCR、视觉模型或后台 Worker。
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
            return self._parse_pdf_sync(file_content)

        content_type = self._guess_content_type(filename)
        elements = partition(file=io.BytesIO(file_content), content_type=content_type)
        return self._serialize(elements)

    def _parse_pdf_sync(self, file_content: bytes) -> str:
        """PDF：pypdf 文本层探针 + pdfminer 布局分析（字号标题检测）。

        损坏 PDF -> PdfReadError（冒泡为路由层 FILE_PARSE_FAILED）；
        合法但无文本层（扫描版）-> 返回 ""（路由层 KNOWLEDGE_PDF_NO_TEXT_LAYER）；
        有文本层 -> pdfminer extract_pages 取 LTTextBox + 字号 -> 序列化。

        不走 unstructured.partition.pdf：它无条件 import unstructured_inference
       （拖 torch/opencv/onnxruntime 视觉模型栈），违反 C5“不引视觉模型”约束。
        """
        reader = PdfReader(io.BytesIO(file_content))
        if not any((page.extract_text() or "").strip() for page in reader.pages):
            return ""
        return self._pdfminer_serialize(file_content)

    @staticmethod
    def _pdfminer_serialize(file_content: bytes) -> str:
        """pdfminer 布局分析：按行字号检测标题（大于正文字号 + 短文本 -> `#`）。"""
        from collections import Counter

        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTChar, LTTextLine

        def _iter_lines(layout):
            for el in layout:
                if isinstance(el, LTTextLine):
                    yield el
                elif hasattr(el, "__iter__"):
                    yield from _iter_lines(el)

        lines: list[tuple[str, float]] = []
        for page in extract_pages(io.BytesIO(file_content)):
            for line in _iter_lines(page):
                text = line.get_text().strip()
                if not text:
                    continue
                sizes = [c.size for c in line if isinstance(c, LTChar)]
                avg = sum(sizes) / len(sizes) if sizes else 0.0
                lines.append((text, avg))
        if not lines:
            return ""
        # 正文字号 = 最常见（众数）；平局取较小字号（标题恒 >= 正文）
        size_counts = Counter(round(s, 1) for _, s in lines if s > 0)
        body_size = (
            sorted(size_counts.items(), key=lambda x: (-x[1], x[0]))[0][0]
            if size_counts else 0.0
        )
        parts: list[str] = []
        for text, size in lines:
            is_title = (
                body_size > 0
                and size > body_size + 0.5  # 明显大于正文
                and len(text.split()) <= 12  # 短文本（启发式，同 is_possible_title）
            )
            parts.append(f"# {text}" if is_title else text)
        return "\n\n".join(parts)

    @staticmethod
    def _serialize(elements) -> str:
        """元素类型感知序列化：Title->`# `、ListItem->`- `，其余原样；\\n\\n 拼接。

        chunk_by_title 的章节感知依赖 `#` 标题边界；只给 Title 元素加前缀，不从
        普通段落发明标题。partition_md("# x") 已剥离 `#`，故补回无双重前缀。
        """
        parts: list[str] = []
        for e in elements:
            text = (getattr(e, "text", None) or "").strip()
            if not text:
                continue
            if e.category == "Title":
                parts.append(f"# {text}")
            elif e.category == "ListItem":
                parts.append(f"- {text}")
            else:  # NarrativeText / UncategorizedText / Table / PageBreak 原样
                parts.append(text)
        return "\n\n".join(parts)

    @classmethod
    def _guess_content_type(cls, filename: str) -> str:
        ext = cls.extension(filename)
        allowed = cls.SUPPORTED_MIME_TYPES.get(ext)
        if allowed is None:
            raise ValueError("unsupported document type")
        return cls.PARTITION_CONTENT_TYPES[ext]
