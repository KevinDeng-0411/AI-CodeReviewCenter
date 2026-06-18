package com.aicenter.ai.service;

import com.aicenter.common.enums.SectionType;
import com.aicenter.common.exception.BusinessException;
import com.aicenter.model.entity.AiReadmeDocument;
import com.aicenter.model.mapper.AiReadmeDocumentMapper;
import com.aicenter.model.vo.AiReadmeVO;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import dev.langchain4j.model.chat.ChatLanguageModel;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * AIReadMe 文档生成服务
 * <p>
 * 扫描项目结构，按 6 个章节（技术架构、核心流程、开发指南、
 * 项目结构、业务知识、历史经验）依次生成文档内容。
 *
 * @author aicenter
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AiReadmeService {

    private final ChatLanguageModel chatModel;
    private final AiReadmeDocumentMapper documentMapper;

    /**
     * 生成 AIReadMe 文档（6 个章节）
     *
     * @param projectName 项目名称
     * @param projectInfo 项目信息（pom.xml、目录结构、关键类等）
     * @return 6 个章节的文档
     */
    public List<AiReadmeVO> generate(String projectName, String projectInfo) {
        // 删除旧版本
        documentMapper.delete(new LambdaQueryWrapper<AiReadmeDocument>()
                .eq(AiReadmeDocument::getProjectName, projectName));

        List<AiReadmeVO> results = new ArrayList<>();

        for (SectionType section : SectionType.values()) {
            log.info("开始生成章节: project={}, section={}", projectName, section.getDesc());
            String content = generateSection(section, projectName, projectInfo);

            AiReadmeDocument doc = new AiReadmeDocument()
                    .setProjectName(projectName)
                    .setSection(section.getCode())
                    .setContent(content)
                    .setVersion(1);
            documentMapper.insert(doc);

            AiReadmeVO vo = new AiReadmeVO();
            vo.setId(doc.getId());
            vo.setProjectName(projectName);
            vo.setSection(section.getCode());
            vo.setSectionName(section.getDesc());
            vo.setContent(content);
            vo.setVersion(1);
            results.add(vo);

            log.info("章节生成完成: section={}, length={}", section.getDesc(), content.length());
        }

        return results;
    }

    /**
     * 生成单个章节
     */
    private String generateSection(SectionType section, String projectName, String projectInfo) {
        String prompt = buildSectionPrompt(section, projectName, projectInfo);
        return chatModel.generate(prompt);
    }

    /**
     * 构建章节 Prompt
     */
    private String buildSectionPrompt(SectionType section, String projectName, String projectInfo) {
        return switch (section) {
            case ARCHITECTURE -> """
                    你是一名资深 Java 架构师。请根据以下项目信息，生成「技术架构」章节的文档。
                    内容包括：技术栈选型说明、架构分层设计、各层职责、关键技术决策及理由。

                    项目名称：%s
                    项目信息：%s

                    要求：专业、准确、可落地，便于新成员快速理解架构。使用 Markdown 格式。
                    """.formatted(projectName, projectInfo);

            case CORE_FLOW -> """
                    你是一名资深 Java 架构师。请根据以下项目信息，生成「核心流程」章节的文档。
                    内容包括：关键业务流程的文字序列描述、数据在各层之间的流转。
                    使用 "用户 → Controller → Service → Mapper → DB" 的形式描述。

                    项目名称：%s
                    项目信息：%s

                    要求：清晰明了，新成员可据此理解系统核心运作方式。使用 Markdown 格式。
                    """.formatted(projectName, projectInfo);

            case DEV_GUIDE -> """
                    你是一名资深 Java 开发者。请根据以下项目信息，生成「开发指南」章节的文档。
                    内容包括：环境搭建步骤、本地启动命令、Docker Compose 使用、
                    开发规范（命名约定、代码风格）、调试方法、常见问题排查。

                    项目名称：%s
                    项目信息：%s

                    要求：可直接照做，对新人友好。使用 Markdown 格式。
                    """.formatted(projectName, projectInfo);

            case STRUCTURE -> """
                    你是一名资深 Java 开发者。请根据以下项目信息，生成「项目结构」章节的文档。
                    内容包括：模块划分说明、包结构及含义、各模块依赖关系、
                    关键目录说明、配置文件说明。

                    项目名称：%s
                    项目信息：%s

                    要求：层次清晰，可作为代码导航的索引。使用 Markdown 格式。
                    """.formatted(projectName, projectInfo);

            case BUSINESS -> """
                    你是一名资深业务分析师。请根据以下项目信息，生成「业务知识」章节的文档。
                    内容包括：核心业务领域术语、业务规则摘要、关键实体关系、
                    业务流程与状态机描述、业务边界说明。

                    项目名称：%s
                    项目信息：%s

                    要求：非技术人员也能理解核心业务概念。使用 Markdown 格式。
                    """.formatted(projectName, projectInfo);

            case EXPERIENCE -> """
                    你是一名资深 Java 技术专家。请根据以下项目信息，生成「历史经验」章节的文档。
                    内容包括：已知的技术陷阱与坑点、性能调优经验、架构演进中的重要决策、
                    最佳实践建议、线上问题复盘要点。

                    项目名称：%s
                    项目信息：%s

                    要求：基于项目技术栈推断常见问题，帮助团队少走弯路。使用 Markdown 格式。
                    """.formatted(projectName, projectInfo);
        };
    }

    /**
     * 获取指定项目的 AIReadMe
     */
    public List<AiReadmeVO> getByProject(String projectName) {
        List<AiReadmeDocument> docs = documentMapper.selectList(
                new LambdaQueryWrapper<AiReadmeDocument>()
                        .eq(AiReadmeDocument::getProjectName, projectName)
                        .orderByAsc(AiReadmeDocument::getSection)
        );

        List<AiReadmeVO> results = new ArrayList<>();
        for (AiReadmeDocument doc : docs) {
            AiReadmeVO vo = new AiReadmeVO();
            vo.setId(doc.getId());
            vo.setProjectName(doc.getProjectName());
            vo.setSection(doc.getSection());
            vo.setSectionName(getSectionDesc(doc.getSection()));
            vo.setContent(doc.getContent());
            vo.setVersion(doc.getVersion());
            results.add(vo);
        }
        return results;
    }

    private String getSectionDesc(String sectionCode) {
        try {
            return SectionType.valueOf(sectionCode).getDesc();
        } catch (Exception e) {
            return sectionCode;
        }
    }
}
