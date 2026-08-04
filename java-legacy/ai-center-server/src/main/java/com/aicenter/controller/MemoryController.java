package com.aicenter.controller;

import com.aicenter.ai.memory.LongTermMemoryManager;
import com.aicenter.common.result.Result;
import com.aicenter.model.dto.MemorySaveRequest;
import com.aicenter.model.entity.LongTermMemory;
import com.aicenter.model.vo.LongTermMemoryVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 记忆管理控制器
 *
 * @author aicenter
 */
@RestController
@RequestMapping("/api/memory")
@RequiredArgsConstructor
@Tag(name = "记忆管理", description = "长期记忆管理与语义检索")
public class MemoryController {

    private final LongTermMemoryManager memoryManager;

    @PostMapping("/long-term")
    @Operation(summary = "保存长期记忆", description = "手动录入长期记忆（自动向量化存储）")
    public Result<LongTermMemory> save(@RequestBody MemorySaveRequest request) {
        LongTermMemory memory = memoryManager.saveMemory(
                request.getSessionId(),
                request.getContent(),
                request.getMemoryType(),
                request.getMetadata()
        );
        return Result.success(memory);
    }

    @GetMapping("/long-term/search")
    @Operation(summary = "语义搜索记忆", description = "基于语义相似度检索长期记忆")
    public Result<List<LongTermMemoryVO>> search(
            @RequestParam String query,
            @RequestParam(defaultValue = "0.6") double threshold,
            @RequestParam(defaultValue = "5") int topK) {
        List<LongTermMemoryVO> results = memoryManager.recall(query, threshold, topK);
        return Result.success(results);
    }

    @DeleteMapping("/long-term/{id}")
    @Operation(summary = "删除长期记忆", description = "删除指定长期记忆")
    public Result<Void> delete(@PathVariable Long id) {
        memoryManager.deleteMemory(id);
        return Result.success();
    }
}
