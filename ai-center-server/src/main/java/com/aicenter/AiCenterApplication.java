package com.aicenter;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * AI Center — 工作室 AI 中心
 * <p>
 * AI 驱动的研发效能平台，提供 AI Code Review、AI 单元测试生成、
 * AIReadMe 文档生成、智能问答知识库等功能。
 *
 * @author aicenter
 */
@SpringBootApplication
@MapperScan("com.aicenter.model.mapper")
public class AiCenterApplication {

    public static void main(String[] args) {
        SpringApplication.run(AiCenterApplication.class, args);
    }
}
