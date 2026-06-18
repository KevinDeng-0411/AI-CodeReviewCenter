package com.aicenter.ai.service;

import lombok.extern.slf4j.Slf4j;
import org.apache.tika.Tika;
import org.apache.tika.exception.TikaException;
import org.apache.tika.metadata.Metadata;
import org.apache.tika.parser.AutoDetectParser;
import org.apache.tika.parser.ParseContext;
import org.apache.tika.parser.Parser;
import org.apache.tika.sax.BodyContentHandler;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.xml.sax.SAXException;

import java.io.IOException;
import java.io.InputStream;

/**
 * 文档解析服务 — 基于 Apache Tika 的多格式文本提取
 * <p>
 * 支持格式: PDF, Word (.doc/.docx), HTML, Markdown, Plain Text,
 * Excel (.xls/.xlsx), PowerPoint, RTF, EPUB, OpenDocument 等
 *
 * @author aicenter
 */
@Slf4j
@Service
public class DocumentParserService {

    private final Tika tika = new Tika();

    /**
     * 快速提取文件文本（自动检测格式）
     */
    public String parse(MultipartFile file) throws IOException, TikaException, SAXException {
        try (InputStream is = file.getInputStream()) {
            String text = tika.parseToString(is);
            log.info("文档解析完成: fileName={}, textLength={}",
                    file.getOriginalFilename(), text.length());
            return text;
        }
    }

    /**
     * 提取文本并返回元数据（文件名、作者、页数等）
     */
    public ParseResult parseWithMetadata(MultipartFile file)
            throws IOException, TikaException, SAXException {
        BodyContentHandler handler = new BodyContentHandler(-1);
        Metadata metadata = new Metadata();
        ParseContext context = new ParseContext();
        Parser parser = new AutoDetectParser();

        try (InputStream is = file.getInputStream()) {
            parser.parse(is, handler, metadata, context);
        }

        String text = handler.toString();
        log.info("文档解析完成: fileName={}, textLength={}, contentType={}",
                file.getOriginalFilename(), text.length(),
                metadata.get("Content-Type"));

        return new ParseResult(text, metadata);
    }

    /**
     * 解析结果
     */
    public record ParseResult(String text, Metadata metadata) {
        public String getTitle() {
            String title = metadata.get("title");
            return (title != null && !title.isBlank()) ? title : "未命名文档";
        }

        public String getAuthor() {
            return metadata.get("author");
        }
    }
}
