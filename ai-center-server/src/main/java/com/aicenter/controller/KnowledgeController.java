package com.aicenter.controller;

import com.aicenter.ai.rag.HybridRetriever;
import com.aicenter.ai.service.RagService;
import com.aicenter.common.result.Result;
import com.aicenter.model.dto.KnowledgeUploadRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

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

    @PostMapping("/upload")
    @Operation(summary = "上传知识文档", description = "上传文档，自动语义分块并向量化入库")
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
                "message", "文档已成功分块并入库"
        ));
    }

    @PostMapping("/search")
    @Operation(summary = "RAG 检索", description = "通过查询重写 + BM25+向量混合检索，返回相关知识文档")
    public Result<List<HybridRetriever.ScoredDocument>> search(
            @RequestBody Map<String, Object> request) {
        String query = (String) request.get("query");
        int topK = request.containsKey("topK") ? (Integer) request.get("topK") : 5;
        List<HybridRetriever.ScoredDocument> results = ragService.search(query, topK);
        return Result.success(results);
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除知识文档", description = "删除指定知识文档")
    public Result<Void> delete(@PathVariable Long id) {
        ragService.deleteDocument(id);
        return Result.success();
    }
}
