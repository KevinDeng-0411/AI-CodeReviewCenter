package com.aicenter.common.result;

import lombok.Data;

import java.io.Serializable;

/**
 * 统一响应结果
 *
 * @author aicenter
 */
@Data
public class Result<T> implements Serializable {

    private static final long serialVersionUID = 1L;

    /** 状态码：1-成功，0-失败 */
    private Integer code;

    /** 提示信息 */
    private String msg;

    /** 响应数据 */
    private T data;

    public Result() {
    }

    public Result(Integer code, String msg, T data) {
        this.code = code;
        this.msg = msg;
        this.data = data;
    }

    // ======================== 静态工厂方法 ========================

    public static <T> Result<T> success() {
        return new Result<>(1, "success", null);
    }

    public static <T> Result<T> success(T data) {
        return new Result<>(1, "success", data);
    }

    public static <T> Result<T> success(String msg, T data) {
        return new Result<>(1, msg, data);
    }

    public static <T> Result<T> error(String msg) {
        return new Result<>(0, msg, null);
    }

    public static <T> Result<T> error(Integer code, String msg) {
        return new Result<>(code, msg, null);
    }
}
