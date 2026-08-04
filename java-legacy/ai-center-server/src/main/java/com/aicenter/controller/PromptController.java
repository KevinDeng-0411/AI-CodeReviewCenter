package com.aicenter.controller;

import com.aicenter.ai.service.PromptService;
import com.aicenter.common.result.PageResult;
import com.aicenter.common.result.Result;
import com.aicenter.model.dto.PromptTemplateSaveDTO;
import com.aicenter.model.entity.PromptTemplate;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * Prompt 模板管理控制器
 *
 * @author aicenter
 */
@RestController
@RequestMapping("/api/prompts")
@RequiredArgsConstructor
@Tag(name = "Prompt 模板", description = "Prompt 模板管理接口")
public class PromptController {

    private final PromptService promptService;

    @GetMapping
    @Operation(summary = "模板列表", description = "分页查询 Prompt 模板")
    public Result<PageResult<PromptTemplate>> list(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String type) {
        Page<PromptTemplate> result = promptService.list(page, size, type);
        return Result.success(PageResult.of(result.getTotal(), result.getRecords()));
    }

    @PostMapping
    @Operation(summary = "创建模板", description = "创建新的 Prompt 模板")
    public Result<PromptTemplate> create(@RequestBody PromptTemplateSaveDTO dto) {
        PromptTemplate template = new PromptTemplate()
                .setName(dto.getName())
                .setType(dto.getType())
                .setRoleSetting(dto.getRoleSetting())
                .setReviewDimensions(dto.getReviewDimensions())
                .setSeverityLevels(dto.getSeverityLevels())
                .setTemplateBody(dto.getTemplateBody());
        return Result.success(promptService.create(template));
    }

    @PutMapping("/{id}")
    @Operation(summary = "更新模板", description = "更新 Prompt 模板（版本号 +1）")
    public Result<PromptTemplate> update(@PathVariable Long id,
                                          @RequestBody PromptTemplateSaveDTO dto) {
        PromptTemplate template = new PromptTemplate()
                .setId(id)
                .setName(dto.getName())
                .setType(dto.getType())
                .setRoleSetting(dto.getRoleSetting())
                .setReviewDimensions(dto.getReviewDimensions())
                .setSeverityLevels(dto.getSeverityLevels())
                .setTemplateBody(dto.getTemplateBody());
        return Result.success(promptService.update(template));
    }

    @PostMapping("/{id}/activate")
    @Operation(summary = "激活模板", description = "激活指定模板（同类型其他模板将停用）")
    public Result<Void> activate(@PathVariable Long id) {
        promptService.activate(id);
        return Result.success();
    }

    @GetMapping("/{id}/preview")
    @Operation(summary = "预览模板", description = "预览 Prompt 模板渲染效果")
    public Result<String> preview(@PathVariable Long id,
                                   @RequestParam(required = false) String sampleCode) {
        return Result.success(promptService.preview(id, sampleCode));
    }
}
