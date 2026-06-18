package com.aicenter.common.enums;

import lombok.Getter;

/**
 * Code Review 问题严重等级
 *
 * @author aicenter
 */
@Getter
public enum SeverityLevel {

    CRITICAL("Critical", "必须修复，可能导致系统故障、安全漏洞或数据丢失"),
    WARNING("Warning", "建议修复，影响代码质量或存在潜在风险"),
    INFO("Info", "优化建议，可以提升代码优雅度或性能");

    private final String code;
    private final String desc;

    SeverityLevel(String code, String desc) {
        this.code = code;
        this.desc = desc;
    }
}
