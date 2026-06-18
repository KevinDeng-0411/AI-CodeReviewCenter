package com.aicenter.ai.rag;

import com.aicenter.common.constant.AiConstants;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * 语义分块器
 * <p>
 * 按段落 + 语义边界切分文档，保持语义完整性。
 * 支持 Markdown header 感知，在标题处分块。
 *
 * @author aicenter
 */
@Component
public class SemanticChunker {

    private static final int CHUNK_SIZE = AiConstants.DEFAULT_CHUNK_SIZE;
    private static final int CHUNK_OVERLAP = AiConstants.DEFAULT_CHUNK_OVERLAP;

    /**
     * 将文档按语义边界切分为多个块
     *
     * @param content 原始文档内容
     * @return 分块列表
     */
    public List<String> chunk(String content) {
        if (content == null || content.isEmpty()) {
            return List.of();
        }

        List<String> chunks = new ArrayList<>();

        // 1. 先按 Markdown 标题分（## 和 ###）
        List<String> sections = splitByMarkdownHeaders(content);

        // 2. 对每个段落按长度进一步切分
        for (String section : sections) {
            if (section.trim().isEmpty()) continue;

            if (estimateTokens(section) <= CHUNK_SIZE) {
                chunks.add(section.trim());
            } else {
                // 按段落再切分
                chunks.addAll(splitByParagraph(section));
            }
        }

        // 3. 添加重叠块（每个块与前后块有重叠）
        chunks = addOverlap(chunks);

        return chunks;
    }

    /**
     * 按 Markdown 标题分块
     */
    private List<String> splitByMarkdownHeaders(String content) {
        List<String> sections = new ArrayList<>();
        String[] lines = content.split("\n");
        StringBuilder current = new StringBuilder();

        for (String line : lines) {
            if ((line.startsWith("## ") || line.startsWith("### ") || line.startsWith("# "))
                    && !current.isEmpty()) {
                sections.add(current.toString());
                current = new StringBuilder();
            }
            current.append(line).append("\n");
        }
        if (!current.isEmpty()) {
            sections.add(current.toString());
        }

        // 如果只有一个块，原样返回
        if (sections.isEmpty()) {
            sections.add(content);
        }

        return sections;
    }

    /**
     * 按段落进一步切分大块
     */
    private List<String> splitByParagraph(String section) {
        List<String> result = new ArrayList<>();
        StringBuilder buffer = new StringBuilder();

        String[] paragraphs = section.split("\n\n");
        for (String para : paragraphs) {
            if (estimateTokens(buffer.toString()) + estimateTokens(para) > CHUNK_SIZE
                    && !buffer.isEmpty()) {
                result.add(buffer.toString().trim());
                buffer = new StringBuilder();
            }
            buffer.append(para).append("\n\n");
        }
        if (!buffer.isEmpty()) {
            result.add(buffer.toString().trim());
        }
        return result;
    }

    /**
     * 添加块之间的重叠
     */
    private List<String> addOverlap(List<String> chunks) {
        if (chunks.size() <= 1) return chunks;

        List<String> result = new ArrayList<>();
        for (int i = 0; i < chunks.size(); i++) {
            String chunk = chunks.get(i);
            // 从前一块借一些内容作为上下文
            if (i > 0 && CHUNK_OVERLAP > 0) {
                String prev = chunks.get(i - 1);
                int overlapLen = Math.min(CHUNK_OVERLAP * 2, prev.length());
                String overlap = prev.substring(Math.max(0, prev.length() - overlapLen));
                chunk = overlap + "\n\n" + chunk;
            }
            result.add(chunk);
        }
        return result;
    }

    /**
     * 估算 Token 数（中文约 1.5 字符/token）
     */
    private int estimateTokens(String text) {
        return text.length() / 2;
    }
}
