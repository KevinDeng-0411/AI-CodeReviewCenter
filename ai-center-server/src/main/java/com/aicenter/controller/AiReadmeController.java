package com.aicenter.controller;

import com.aicenter.ai.service.AiReadmeService;
import com.aicenter.common.result.Result;
import com.aicenter.model.dto.AiReadmeRequest;
import com.aicenter.model.vo.AiReadmeVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * AIReadMe 文档生成控制器
 *
 * @author aicenter
 */
@RestController
@RequestMapping("/api/ai-readme")
@RequiredArgsConstructor
@Tag(name = "AIReadMe 文档", description = "AI 自动化项目文档生成")
public class AiReadmeController {

    private final AiReadmeService aiReadmeService;

    @PostMapping("/generate")
    @Operation(summary = "生成 AIReadMe", description = "扫描项目并生成 6 章节 AIReadMe 文档")
    public Result<List<AiReadmeVO>> generate(@RequestBody AiReadmeRequest request) {
        // 构建项目信息摘要（实际场景应扫描文件系统）
        String projectInfo = buildProjectInfo(request.getProjectName(), request.getProjectPath());
        List<AiReadmeVO> results = aiReadmeService.generate(
                request.getProjectName(), projectInfo);
        return Result.success(results);
    }

    @GetMapping("/{projectName}")
    @Operation(summary = "获取项目 AIReadMe", description = "获取指定项目的 AIReadMe 文档")
    public Result<List<AiReadmeVO>> getByProject(@PathVariable String projectName) {
        return Result.success(aiReadmeService.getByProject(projectName));
    }

    /**
     * 构建项目信息摘要
     */
    private String buildProjectInfo(String projectName, String projectPath) {
        return String.format("""
                项目名称：%s
                项目路径：%s
                技术栈：Java 17, Spring Boot 3.2, MyBatis-Plus, PostgreSQL, Redis, LangChain4j
                架构：Maven 多模块（common / model / ai / server）
                主要功能：AI Code Review、AI 单元测试生成、AIReadMe 文档生成、智能问答知识库
                """, projectName, projectPath != null ? projectPath : "/projects/" + projectName);
    }
}
