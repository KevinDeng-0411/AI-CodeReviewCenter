package com.aicenter.model.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * AIReadMe 生成请求
 *
 * @author aicenter
 */
@Data
@Schema(description = "AIReadMe 生成请求")
public class AiReadmeRequest {

    @Schema(description = "项目名称", example = "ai-center")
    private String projectName;

    @Schema(description = "项目根路径（服务器本地路径）", example = "/home/projects/ai-center")
    private String projectPath;
}
