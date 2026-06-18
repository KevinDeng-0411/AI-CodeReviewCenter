package com.aicenter.model.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 长期记忆搜索结果视图
 *
 * @author aicenter
 */
@Data
@Schema(description = "长期记忆搜索结果")
public class LongTermMemoryVO {

    @Schema(description = "记忆 ID")
    private Long id;

    @Schema(description = "记忆内容")
    private String content;

    @Schema(description = "记忆类型")
    private String memoryType;

    @Schema(description = "语义相似度分数")
    private Double similarity;

    @Schema(description = "创建时间")
    private LocalDateTime createdAt;
}
