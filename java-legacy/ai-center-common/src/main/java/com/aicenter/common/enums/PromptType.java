package com.aicenter.common.enums;

import lombok.Getter;

/**
 * Prompt 模板类型枚举
 *
 * @author aicenter
 */
@Getter
public enum PromptType {

    CODE_REVIEW("CODE_REVIEW", "代码评审"),
    UNIT_TEST("UNIT_TEST", "单元测试生成"),
    AI_README("AI_README", "AIReadMe 文档生成"),
    CHAT("CHAT", "智能对话");

    private final String code;
    private final String desc;

    PromptType(String code, String desc) {
        this.code = code;
        this.desc = desc;
    }
}
