package com.aicenter.model.mapper;

import com.aicenter.model.entity.ChatMessage;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;

/**
 * 聊天消息 Mapper
 *
 * @author aicenter
 */
@Mapper
public interface ChatMessageMapper extends BaseMapper<ChatMessage> {
}
