package com.aicenter.model.mapper;

import com.aicenter.model.entity.PromptTemplate;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

/**
 * Prompt 模板 Mapper
 *
 * @author aicenter
 */
@Mapper
public interface PromptTemplateMapper extends BaseMapper<PromptTemplate> {
}
