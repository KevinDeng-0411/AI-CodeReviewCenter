package com.aicenter.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * AI 单元测试生成记录实体
 *
 * @author aicenter
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("unit_test_records")
public class UnitTestRecord implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /** 项目名称 */
    private String projectName;

    /** 文件路径 */
    private String filePath;

    /** 原始代码 */
    private String sourceCode;

    /** 生成的测试代码 */
    private String testCode;

    /** 测试框架 */
    private String testFramework;

    /** Prompt 模板 ID */
    private Long promptTemplateId;

    /** AI 模型 */
    private String aiModel;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
