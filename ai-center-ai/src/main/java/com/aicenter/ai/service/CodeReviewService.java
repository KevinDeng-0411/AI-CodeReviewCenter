package com.aicenter.ai.service;

import cn.hutool.json.JSONArray;
import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import com.aicenter.ai.prompt.PromptTemplateManager;
import com.aicenter.common.enums.PromptType;
import com.aicenter.common.exception.BusinessException;
import com.aicenter.model.entity.CodeReviewRecord;
import com.aicenter.model.entity.PromptTemplate;
import com.aicenter.model.mapper.CodeReviewRecordMapper;
import com.aicenter.model.vo.CodeReviewVO;
import com.aicenter.model.vo.ReviewIssueVO;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import dev.langchain4j.model.chat.ChatLanguageModel;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * AI Code Review 服务
 * <p>
 * 基于结构化 Prompt 模板进行代码评审，覆盖 8 个维度、3 级问题分类。
 * 使用 LLM 的 JSON 模式约束输出，保证评审结果结构化。
 *
 * @author aicenter
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class CodeReviewService {

    private final ChatLanguageModel chatModel;
    private final PromptTemplateManager promptManager;
    private final CodeReviewRecordMapper recordMapper;

    /**
     * 执行 AI Code Review
     *
     * @param projectName      项目名称
     * @param filePath         文件路径
     * @param sourceCode       源代码
     * @param promptTemplateId 模板 ID（可选）
     * @return 评审结果
     */
    public CodeReviewVO review(String projectName, String filePath, String sourceCode,
                                Long promptTemplateId) {
        // 1. 获取 Prompt 模板
        PromptTemplate template;
        if (promptTemplateId != null) {
            template = promptManager.getActiveTemplateByName(
                    PromptType.CODE_REVIEW.getCode(), null);
            if (template == null) {
                template = promptManager.getActiveTemplate(PromptType.CODE_REVIEW);
            }
        } else {
            template = promptManager.getActiveTemplate(PromptType.CODE_REVIEW);
        }
        if (template == null) {
            throw new BusinessException("未找到可用的 Code Review Prompt 模板");
        }

        // 2. 渲染 Prompt
        Map<String, String> params = new HashMap<>();
        params.put("source_code", sourceCode);
        String systemPrompt = promptManager.renderSystemPrompt(template, params);

        // 3. 调用 LLM
        log.info("开始 AI Code Review: project={}, file={}, codeLength={}",
                projectName, filePath, sourceCode.length());
        String aiResponse = chatModel.generate(systemPrompt);
        log.info("AI Code Review 完成，响应长度: {}", aiResponse.length());

        // 4. 解析 JSON 结果
        CodeReviewVO vo = parseReviewResult(aiResponse);
        vo.setProjectName(projectName);
        vo.setFilePath(filePath);

        // 5. 持久化评审记录
        CodeReviewRecord record = new CodeReviewRecord()
                .setProjectName(projectName)
                .setFilePath(filePath)
                .setSourceCode(sourceCode)
                .setReviewResult(aiResponse)
                .setIssuesCount(vo.getIssuesCount())
                .setCriticalCount(vo.getCriticalCount())
                .setWarningCount(vo.getWarningCount())
                .setInfoCount(vo.getInfoCount())
                .setPromptTemplateId(template.getId())
                .setAiModel("deepseek-chat");
        recordMapper.insert(record);
        vo.setId(record.getId());

        return vo;
    }

    /**
     * 解析 LLM 返回的 JSON 评审结果
     */
    private CodeReviewVO parseReviewResult(String aiResponse) {
        try {
            // 提取 JSON 部分（LLM 可能包裹在 markdown 代码块中）
            String jsonStr = extractJson(aiResponse);
            JSONObject result = JSONUtil.parseObj(jsonStr);

            CodeReviewVO vo = new CodeReviewVO();
            vo.setScore(result.getInt("score", 0));
            vo.setSummary(result.getStr("summary", ""));

            // 解析问题列表
            JSONArray issuesArr = result.getJSONArray("issues");
            List<ReviewIssueVO> issues = new ArrayList<>();
            int critical = 0, warning = 0, info = 0;

            if (issuesArr != null) {
                for (int i = 0; i < issuesArr.size(); i++) {
                    JSONObject issueJson = issuesArr.getJSONObject(i);
                    ReviewIssueVO issue = new ReviewIssueVO();
                    issue.setDimension(issueJson.getStr("dimension"));
                    issue.setSeverity(issueJson.getStr("severity"));
                    issue.setLineRange(issueJson.getStr("line_range"));
                    issue.setTitle(issueJson.getStr("title"));
                    issue.setDescription(issueJson.getStr("description"));
                    issue.setSuggestion(issueJson.getStr("suggestion"));
                    issue.setFixCode(issueJson.getStr("fix_code"));
                    issues.add(issue);

                    String severity = issue.getSeverity();
                    if ("Critical".equalsIgnoreCase(severity)) critical++;
                    else if ("Warning".equalsIgnoreCase(severity)) warning++;
                    else info++;
                }
            }

            vo.setIssues(issues);
            vo.setIssuesCount(issues.size());
            vo.setCriticalCount(critical);
            vo.setWarningCount(warning);
            vo.setInfoCount(info);

            // 解析亮点
            JSONArray highlightsArr = result.getJSONArray("highlights");
            if (highlightsArr != null) {
                List<String> highlights = new ArrayList<>();
                for (int i = 0; i < highlightsArr.size(); i++) {
                    highlights.add(highlightsArr.getStr(i));
                }
                vo.setHighlights(highlights);
            }

            vo.setAiModel("deepseek-chat");
            return vo;

        } catch (Exception e) {
            log.error("解析 AI 评审结果失败", e);
            CodeReviewVO vo = new CodeReviewVO();
            vo.setSummary("AI 评审结果解析异常，请查看原始响应");
            vo.setIssuesCount(0);
            return vo;
        }
    }

    /**
     * 从 AI 响应中提取 JSON
     */
    private String extractJson(String response) {
        // 尝试提取 ```json ... ``` 代码块
        int start = response.indexOf("```json");
        if (start != -1) {
            start = response.indexOf('\n', start) + 1;
            int end = response.indexOf("```", start);
            if (end != -1) {
                return response.substring(start, end).trim();
            }
        }
        // 尝试提取 { ... } 对象
        start = response.indexOf('{');
        int end = response.lastIndexOf('}');
        if (start != -1 && end != -1 && end > start) {
            return response.substring(start, end + 1).trim();
        }
        return response;
    }

    /**
     * 分页查询评审记录
     */
    public Page<CodeReviewRecord> listRecords(int page, int size, String projectName) {
        LambdaQueryWrapper<CodeReviewRecord> wrapper = new LambdaQueryWrapper<CodeReviewRecord>()
                .eq(projectName != null, CodeReviewRecord::getProjectName, projectName)
                .orderByDesc(CodeReviewRecord::getCreatedAt);
        return recordMapper.selectPage(new Page<>(page, size), wrapper);
    }

    /**
     * 查询评审详情
     */
    public CodeReviewRecord getRecordDetail(Long id) {
        return recordMapper.selectById(id);
    }
}
