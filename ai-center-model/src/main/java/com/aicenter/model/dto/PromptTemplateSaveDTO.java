package com.aicenter.model.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * Prompt 模板保存/更新请求
 *
 * @author aicenter
 */
@Data
@Schema(description = "Prompt 模板保存请求")
public class PromptTemplateSaveDTO {

    @Schema(description = "模板名称", example = "Java Code Review 标准模板")
    private String name;

    @Schema(description = "模板类型", example = "CODE_REVIEW")
    private String type;

    @Schema(description = "角色设定")
    private String roleSetting;

    @Schema(description = "评审维度")
    private String[] reviewDimensions;

    @Schema(description = "问题等级")
    private String[] severityLevels;

    @Schema(description = "模板正文")
    private String templateBody;
}
