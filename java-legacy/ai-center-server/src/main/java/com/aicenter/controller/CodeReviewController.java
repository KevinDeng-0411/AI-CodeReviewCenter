package com.aicenter.controller;

import com.aicenter.ai.service.CodeReviewService;
import com.aicenter.common.exception.BusinessException;
import com.aicenter.common.result.PageResult;
import com.aicenter.common.result.Result;
import com.aicenter.model.dto.CodeReviewRequest;
import com.aicenter.model.entity.CodeReviewRecord;
import com.aicenter.model.vo.CodeReviewVO;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * AI Code Review 控制器
 *
 * @author aicenter
 */
@RestController
@RequestMapping("/api/code-review")
@RequiredArgsConstructor
@Tag(name = "AI Code Review", description = "AI 代码评审相关接口")
public class CodeReviewController {

    private final CodeReviewService codeReviewService;

    @PostMapping("/review")
    @Operation(summary = "提交代码进行 AI 评审", description = "基于 8 维度结构化 Prompt 进行代码评审")
    public Result<CodeReviewVO> review(@RequestBody CodeReviewRequest request) {
        if (request.getSourceCode() == null || request.getSourceCode().isBlank()) {
            throw new BusinessException("源代码不能为空");
        }
        CodeReviewVO result = codeReviewService.review(
                request.getProjectName(),
                request.getFilePath(),
                request.getSourceCode(),
                request.getPromptTemplateId()
        );
        return Result.success(result);
    }

    @GetMapping("/records")
    @Operation(summary = "评审记录列表", description = "分页查询历史评审记录")
    public Result<PageResult<CodeReviewRecord>> listRecords(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String projectName) {
        Page<CodeReviewRecord> result = codeReviewService.listRecords(page, size, projectName);
        return Result.success(PageResult.of(result.getTotal(), result.getRecords()));
    }

    @GetMapping("/records/{id}")
    @Operation(summary = "评审详情", description = "查看某次评审的完整结果")
    public Result<CodeReviewRecord> getDetail(@PathVariable Long id) {
        return Result.success(codeReviewService.getRecordDetail(id));
    }
}
