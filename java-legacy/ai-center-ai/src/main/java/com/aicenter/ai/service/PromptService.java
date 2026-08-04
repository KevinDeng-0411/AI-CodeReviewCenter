package com.aicenter.ai.service;

import com.aicenter.ai.prompt.PromptTemplateManager;
import com.aicenter.common.enums.PromptType;
import com.aicenter.common.exception.BusinessException;
import com.aicenter.model.entity.PromptTemplate;
import com.aicenter.model.mapper.PromptTemplateMapper;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * Prompt 模板管理服务
 *
 * @author aicenter
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class PromptService {

    private final PromptTemplateMapper mapper;
    private final PromptTemplateManager cacheManager;

    /**
     * 分页查询模板列表
     */
    public Page<PromptTemplate> list(int page, int size, String type) {
        LambdaQueryWrapper<PromptTemplate> wrapper = new LambdaQueryWrapper<PromptTemplate>()
                .eq(type != null, PromptTemplate::getType, type)
                .orderByDesc(PromptTemplate::getCreatedAt);
        return mapper.selectPage(new Page<>(page, size), wrapper);
    }

    /**
     * 创建模板
     */
    public PromptTemplate create(PromptTemplate template) {
        template.setVersion(1);
        template.setIsActive(true);
        mapper.insert(template);
        cacheManager.refreshCache();
        return template;
    }

    /**
     * 更新模板
     */
    public PromptTemplate update(PromptTemplate template) {
        PromptTemplate existing = mapper.selectById(template.getId());
        if (existing == null) {
            throw new BusinessException("模板不存在");
        }
        template.setVersion(existing.getVersion() + 1);
        mapper.updateById(template);
        cacheManager.refreshCache();
        return mapper.selectById(template.getId());
    }

    /**
     * 激活模板
     */
    public void activate(Long id) {
        PromptTemplate template = mapper.selectById(id);
        if (template == null) {
            throw new BusinessException("模板不存在");
        }
        // 先停用同类型其他模板
        LambdaQueryWrapper<PromptTemplate> wrapper = new LambdaQueryWrapper<PromptTemplate>()
                .eq(PromptTemplate::getType, template.getType())
                .ne(PromptTemplate::getId, id);
        List<PromptTemplate> others = mapper.selectList(wrapper);
        for (PromptTemplate other : others) {
            other.setIsActive(false);
            mapper.updateById(other);
        }
        // 激活当前
        template.setIsActive(true);
        mapper.updateById(template);
        cacheManager.refreshCache();
    }

    /**
     * 预览模板效果
     */
    public String preview(Long id, String sampleCode) {
        PromptTemplate template = mapper.selectById(id);
        if (template == null) {
            throw new BusinessException("模板不存在");
        }
        return cacheManager.render(template,
                java.util.Map.of("source_code", sampleCode != null ? sampleCode : "// 示例代码"));
    }
}
