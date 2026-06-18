package com.aicenter.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Knife4j / Swagger3 API 文档配置
 *
 * @author aicenter
 */
@Configuration
public class Knife4jConfig {

    @Bean
    public OpenAPI aiCenterOpenApi() {
        return new OpenAPI()
                .info(new Info()
                        .title("AI Center API 文档")
                        .description("工作室 AI 中心 — AI 驱动的研发效能平台")
                        .version("1.0.0")
                        .contact(new Contact()
                                .name("AI Center Team")));
    }
}
