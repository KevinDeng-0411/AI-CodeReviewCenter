package com.aicenter.model.mapper;

import com.aicenter.model.entity.ChatConversation;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

/**
 * 会话 Mapper
 *
 * @author aicenter
 */
@Mapper
public interface ChatConversationMapper extends BaseMapper<ChatConversation> {
}
