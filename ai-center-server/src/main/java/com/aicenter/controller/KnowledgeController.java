package com.aicenter.controller;

import com.aicenter.ai.rag.HybridRetriever;
import com.aicenter.ai.service.DocumentParserService;
import com.aicenter.ai.service.RagService;
import com.aicenter.common.result.Result;
import com.aicenter.model.dto.KnowledgeUploadRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 知识库管理控制器
 *
 * @author aicenter
 */
@RestController
@RequestMapping("/api/knowledge")
@RequiredArgsConstructor
@Tag(name = "知识库", description = "知识文档管理与 RAG 检索")
public class KnowledgeController {

    private final RagService ragService;
    private final DocumentParserService documentParserService;

    @PostMapping("/upload")
    @Operation(summary = "上传知识文档（文本）", description = "上传文本内容，自动语义分块并向量化入库(Pinecone)")
    public Result<Map<String, Object>> upload(@RequestBody KnowledgeUploadRequest request) {
        int chunkCount = ragService.uploadDocument(
                request.getTitle(),
                request.getContent(),
                request.getSourceType(),
                request.getProjectName()
        );
        return Result.success(Map.of(
                "title", request.getTitle(),
                "chunks", chunkCount,
                "message", "文档已成功分块并存入 Pinecone"
        ));
    }

    @PostMapping("/upload-file")
    @Operation(summary = "上传文档文件", description = "上传 PDF/Word/HTML 等文件，Apache Tika 自动提取文本后分块向量化")
    public Result<Map<String, Object>> uploadFile(
            @RequestParam("file") MultipartFile file,
            @RequestParam(required = false) String projectName,
            @RequestParam(defaultValue = "MANUAL") String sourceType) {
        try {
            DocumentParserService.ParseResult parseResult =
                    documentParserService.parseWithMetadata(file);
            String title = parseResult.getTitle();
            if (title == null || title.isBlank()) {
                title = file.getOriginalFilename();
            }
            int chunkCount = ragService.uploadDocument(
                    title, parseResult.text(), sourceType, projectName);

            return Result.success(Map.of(
                    "fileName", file.getOriginalFilename(),
                    "title", title,
                    "contentLength", parseResult.text().length(),
                    "chunks", chunkCount,
                    "message", "文件已成功解析、分块并存入 Pinecone"
            ));
        } catch (Exception e) {
            return Result.error("文件解析失败: " + e.getMessage());
        }
    }

    @PostMapping("/search")
    @Operation(summary = "RAG 检索", description = "查询重写 + BM25(PostgreSQL)+向量(PGVector) 混合检索，含来源追溯")
    public Result<Map<String, Object>> search(
            @RequestBody Map<String, Object> request) {
        String query = (String) request.get("query");
        int topK = request.containsKey("topK") ? (Integer) request.get("topK") : 5;
        List<HybridRetriever.ScoredDocument> results = ragService.search(query, topK);

        // 格式化结果，含来源信息
        List<Map<String, Object>> formattedResults = new ArrayList<>();
        Map<String, Integer> sourceStats = new HashMap<>();

        for (var doc : results) {
            String sourceType = doc.document().getSourceType();
            sourceStats.merge(sourceType, 1, Integer::sum);

            formattedResults.add(Map.of(
                    "fusionScore", doc.fusionScore(),
                    "bm25Score", doc.bm25Score(),
                    "vectorScore", doc.vectorScore(),
                    "matchType", doc.matchType(),
                    "document", Map.of(
                            "id", doc.document().getId(),
                            "title", doc.document().getTitle(),
                            "chunkIndex", doc.document().getChunkIndex(),
                            "chunkContent", doc.document().getChunkContent(),
                            "sourceType", sourceType,
                            "projectName", doc.document().getProjectName() != null
                                    ? doc.document().getProjectName() : ""
                    )
            ));
        }

        return Result.success(Map.of(
                "query", query,
                "totalResults", formattedResults.size(),
                "results", formattedResults,
                "sourceStats", sourceStats
        ));
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除知识文档", description = "删除指定知识文档（MySQL + Pinecone）")
    public Result<Void> delete(@PathVariable Long id) {
        ragService.deleteDocument(id);
        return Result.success();
    }
}
