package com.aicenter.common.enums;

import lombok.Getter;

/**
 * 长期记忆类型
 *
 * @author aicenter
 */
@Getter
public enum MemoryType {

    FACT("FACT", "事实信息"),
    PREFERENCE("PREFERENCE", "用户偏好"),
    KNOWLEDGE("KNOWLEDGE", "知识条目"),
    EXPERIENCE("EXPERIENCE", "历史经验");

    private final String code;
    private final String desc;

    MemoryType(String code, String desc) {
        this.code = code;
        this.desc = desc;
    }
}
