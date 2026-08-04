package com.aicenter.model.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * AIReadMe 文档视图
 *
 * @author aicenter
 */
@Data
@Schema(description = "AIReadMe 文档")
public class AiReadmeVO {

    @Schema(description = "文档 ID")
    private Long id;

    @Schema(description = "项目名称")
    private String projectName;

    @Schema(description = "章节编码")
    private String section;

    @Schema(description = "章节名称", example = "技术架构")
    private String sectionName;

    @Schema(description = "章节内容")
    private String content;

    @Schema(description = "版本号")
    private Integer version;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
