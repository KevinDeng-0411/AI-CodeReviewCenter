package com.aicenter.common.exception;

import lombok.Getter;

/**
 * 业务异常
 *
 * @author aicenter
 */
@Getter
public class BusinessException extends RuntimeException {

    private final Integer code;

    public BusinessException(String message) {
        super(message);
        this.code = 0;
    }

    public BusinessException(Integer code, String message) {
        super(message);
        this.code = code;
    }
}
