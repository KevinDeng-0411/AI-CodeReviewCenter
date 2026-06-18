package com.aicenter.common.enums;

import lombok.Getter;

/**
 * AIReadMe 章节类型
 *
 * @author aicenter
 */
@Getter
public enum SectionType {

    ARCHITECTURE("ARCHITECTURE", "技术架构"),
    CORE_FLOW("CORE_FLOW", "核心流程"),
    DEV_GUIDE("DEV_GUIDE", "开发指南"),
    STRUCTURE("STRUCTURE", "项目结构"),
    BUSINESS("BUSINESS", "业务知识"),
    EXPERIENCE("EXPERIENCE", "历史经验");

    private final String code;
    private final String desc;

    SectionType(String code, String desc) {
        this.code = code;
        this.desc = desc;
    }
}
