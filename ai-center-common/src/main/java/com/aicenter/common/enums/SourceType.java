package com.aicenter.common.enums;

import lombok.Getter;

/**
 * 知识文档来源类型
 *
 * @author aicenter
 */
@Getter
public enum SourceType {

    AI_README("AI_README", "AI 生成的 README"),
    MANUAL("MANUAL", "手动上传"),
    CODE("CODE", "代码文件"),
    DOC("DOC", "文档文件");

    private final String code;
    private final String desc;

    SourceType(String code, String desc) {
        this.code = code;
        this.desc = desc;
    }
}
