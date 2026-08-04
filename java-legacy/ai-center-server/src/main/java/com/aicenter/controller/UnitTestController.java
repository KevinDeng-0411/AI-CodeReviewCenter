package com.aicenter.controller;

import com.aicenter.ai.service.UnitTestService;
import com.aicenter.common.exception.BusinessException;
import com.aicenter.common.result.PageResult;
import com.aicenter.common.result.Result;
import com.aicenter.model.dto.UnitTestRequest;
import com.aicenter.model.entity.UnitTestRecord;
import com.aicenter.model.vo.UnitTestVO;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * AI 单元测试生成控制器
 *
 * @author aicenter
 */
@RestController
@RequestMapping("/api/unit-test")
@RequiredArgsConstructor
@Tag(name = "AI 单元测试", description = "AI 单元测试生成相关接口")
public class UnitTestController {

    private final UnitTestService unitTestService;

    @PostMapping("/generate")
    @Operation(summary = "生成单元测试", description = "基于源代码自动生成 JUnit 5 单元测试")
    public Result<UnitTestVO> generate(@RequestBody UnitTestRequest request) {
        if (request.getSourceCode() == null || request.getSourceCode().isBlank()) {
            throw new BusinessException("源代码不能为空");
        }
        UnitTestVO result = unitTestService.generate(
                request.getProjectName(),
                request.getFilePath(),
                request.getSourceCode(),
                request.getTestFramework(),
                request.getPromptTemplateId()
        );
        return Result.success(result);
    }

    @GetMapping("/records")
    @Operation(summary = "生成记录列表", description = "分页查询历史生成记录")
    public Result<PageResult<UnitTestRecord>> listRecords(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String projectName) {
        Page<UnitTestRecord> result = unitTestService.listRecords(page, size, projectName);
        return Result.success(PageResult.of(result.getTotal(), result.getRecords()));
    }

    @GetMapping("/records/{id}")
    @Operation(summary = "生成详情", description = "查看某次生成的完整结果")
    public Result<UnitTestRecord> getDetail(@PathVariable Long id) {
        return Result.success(unitTestService.getRecordDetail(id));
    }
}
