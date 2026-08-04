package com.aicenter.ai.service;

import com.aicenter.ai.prompt.PromptTemplateManager;
import com.aicenter.common.enums.PromptType;
import com.aicenter.common.exception.BusinessException;
import com.aicenter.model.entity.PromptTemplate;
import com.aicenter.model.entity.UnitTestRecord;
import com.aicenter.model.mapper.UnitTestRecordMapper;
import com.aicenter.model.vo.UnitTestVO;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import dev.langchain4j.model.chat.ChatLanguageModel;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.Map;

/**
 * AI 单元测试生成服务
 * <p>
 * 基于源代码自动生成 JUnit 5 单元测试，覆盖正常/边界/异常场景。
 *
 * @author aicenter
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class UnitTestService {

    private final ChatLanguageModel chatModel;
    private final PromptTemplateManager promptManager;
    private final UnitTestRecordMapper recordMapper;

    /**
     * 生成单元测试
     */
    public UnitTestVO generate(String projectName, String filePath, String sourceCode,
                                String testFramework, Long promptTemplateId) {
        // 1. 获取模板
        PromptTemplate template;
        if (promptTemplateId != null) {
            template = promptManager.getActiveTemplate(PromptType.UNIT_TEST);
        } else {
            template = promptManager.getActiveTemplate(PromptType.UNIT_TEST);
        }
        if (template == null) {
            // 使用内置默认 Prompt
            template = buildDefaultUnitTestTemplate();
        }

        // 2. 渲染 Prompt
        Map<String, String> params = new HashMap<>();
        params.put("source_code", sourceCode);
        params.put("test_framework", testFramework != null ? testFramework : "JUnit5");
        String prompt = promptManager.renderSystemPrompt(template, params);

        // 3. 调用 LLM
        log.info("开始生成单元测试: project={}, file={}, framework={}",
                projectName, filePath, testFramework);
        String testCode = chatModel.generate(prompt);
        log.info("单元测试生成完成，代码长度: {}", testCode.length());

        // 提取代码块
        testCode = extractCodeBlock(testCode);

        // 4. 持久化
        UnitTestRecord record = new UnitTestRecord()
                .setProjectName(projectName)
                .setFilePath(filePath)
                .setSourceCode(sourceCode)
                .setTestCode(testCode)
                .setTestFramework(testFramework != null ? testFramework : "JUnit5")
                .setPromptTemplateId(template.getId())
                .setAiModel("deepseek-chat");
        recordMapper.insert(record);

        // 5. 返回
        UnitTestVO vo = new UnitTestVO();
        vo.setId(record.getId());
        vo.setProjectName(projectName);
        vo.setFilePath(filePath);
        vo.setSourceCode(sourceCode);
        vo.setTestCode(testCode);
        vo.setTestFramework(record.getTestFramework());
        vo.setAiModel("deepseek-chat");
        return vo;
    }

    /**
     * 分页查询生成记录
     */
    public Page<UnitTestRecord> listRecords(int page, int size, String projectName) {
        LambdaQueryWrapper<UnitTestRecord> wrapper = new LambdaQueryWrapper<UnitTestRecord>()
                .eq(projectName != null, UnitTestRecord::getProjectName, projectName)
                .orderByDesc(UnitTestRecord::getCreatedAt);
        return recordMapper.selectPage(new Page<>(page, size), wrapper);
    }

    /**
     * 查询生成详情
     */
    public UnitTestRecord getRecordDetail(Long id) {
        return recordMapper.selectById(id);
    }

    /**
     * 从响应中提取代码块
     */
    private String extractCodeBlock(String response) {
        int start = response.indexOf("```java");
        if (start != -1) {
            start = response.indexOf('\n', start) + 1;
            int end = response.indexOf("```", start);
            if (end != -1) {
                return response.substring(start, end).trim();
            }
        }
        return response;
    }

    /**
     * 内置默认单测生成模板
     */
    private PromptTemplate buildDefaultUnitTestTemplate() {
        PromptTemplate t = new PromptTemplate();
        t.setId(0L);
        t.setRoleSetting("你是一名资深 Java 测试工程师，擅长编写高质量单元测试。");
        t.setTemplateBody(
                "请为以下 Java 代码生成完整的 JUnit 5 单元测试。\n\n" +
                "## 测试要求\n" +
                "1. 使用 {{test_framework}} 框架\n" +
                "2. 使用 Mockito 进行 Mock\n" +
                "3. 覆盖正常路径、边界条件、异常场景\n" +
                "4. 遵循 AAA 模式（Arrange-Act-Assert）\n" +
                "5. 测试方法命名清晰，包含场景描述\n" +
                "6. 目标覆盖率 > 80%\n\n" +
                "## 源代码\n" +
                "```java\n{{source_code}}\n```\n\n" +
                "请只输出测试代码，使用 ```java 代码块包裹。"
        );
        return t;
    }
}
