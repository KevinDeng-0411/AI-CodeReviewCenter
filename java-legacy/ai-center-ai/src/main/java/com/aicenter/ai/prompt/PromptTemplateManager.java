package com.aicenter.ai.prompt;

import cn.hutool.json.JSONUtil;
import com.aicenter.common.enums.PromptType;
import com.aicenter.model.entity.PromptTemplate;
import com.aicenter.model.mapper.PromptTemplateMapper;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Prompt 模板管理器
 * <p>
 * 加载并管理 Prompt 模板，支持占位符替换。
 * 内置本地缓存，减少数据库查询。
 *
 * @author aicenter
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class PromptTemplateManager {

    private final PromptTemplateMapper promptTemplateMapper;

    /** 本地模板缓存：type → template */
    private final Map<String, PromptTemplate> templateCache = new ConcurrentHashMap<>();

    @PostConstruct
    public void init() {
        refreshCache();
        log.info("Prompt 模板加载完成，共 {} 个模板", templateCache.size());
    }

    /**
     * 刷新模板缓存
     */
    public void refreshCache() {
        templateCache.clear();
        var templates = promptTemplateMapper.selectList(
                new LambdaQueryWrapper<PromptTemplate>()
                        .eq(PromptTemplate::getIsActive, true)
        );
        for (PromptTemplate t : templates) {
            templateCache.put(t.getType(), t);
        }
        log.debug("模板缓存已刷新");
    }

    /**
     * 获取指定类型的激活模板
     */
    public PromptTemplate getActiveTemplate(PromptType type) {
        return templateCache.get(type.getCode());
    }

    /**
     * 获取指定类型的激活模板（按名称精准匹配）
     */
    public PromptTemplate getActiveTemplateByName(String type, String name) {
        return promptTemplateMapper.selectOne(
                new LambdaQueryWrapper<PromptTemplate>()
                        .eq(PromptTemplate::getType, type)
                        .eq(PromptTemplate::getName, name)
                        .eq(PromptTemplate::getIsActive, true)
        );
    }

    /**
     * 渲染模板：将占位符替换为实际值
     *
     * @param template 模板实体
     * @param params   参数 Map（key → value）
     * @return 渲染后的完整 Prompt
     */
    public String render(PromptTemplate template, Map<String, String> params) {
        String body = template.getTemplateBody();
        if (params == null || params.isEmpty()) {
            return buildFullPrompt(template, body);
        }
        for (Map.Entry<String, String> entry : params.entrySet()) {
            body = body.replace("{{" + entry.getKey() + "}}", entry.getValue());
        }
        return buildFullPrompt(template, body);
    }

    /**
     * 构建完整 Prompt（角色设定 + 模板体）
     */
    private String buildFullPrompt(PromptTemplate template, String renderedBody) {
        return renderedBody;
    }

    /**
     * 渲染模板为 ChatMessage 列表（用于 LangChain4j）
     */
    public String renderSystemPrompt(PromptTemplate template, Map<String, String> params) {
        String roleSetting = template.getRoleSetting();
        String body = render(template, params);
        return roleSetting + "\n\n" + body;
    }

    /**
     * 渲染模板的 JSON 输出约束（用于结构化输出）
     */
    public String buildJsonSchemaConstraint(PromptTemplate template) {
        if (template.getSeverityLevels() == null || template.getReviewDimensions() == null) {
            return "";
        }
        return JSONUtil.createObj()
                .set("dimensions", template.getReviewDimensions())
                .set("severity_levels", template.getSeverityLevels())
                .toString();
    }
}
