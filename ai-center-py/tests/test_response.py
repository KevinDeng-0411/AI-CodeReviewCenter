"""P0：统一响应 Result / PageResult 结构。"""

from app.core.response import PageResult, Result


def test_result_ok():
    r = Result.ok({"a": 1})
    assert r.code == 1
    assert r.msg == "success"
    assert r.data == {"a": 1}


def test_result_ok_no_data():
    r = Result.ok()
    assert r.code == 1
    assert r.data is None


def test_result_error():
    r = Result.error("出错了")
    assert r.code == 0
    assert r.msg == "出错了"
    assert r.data is None


def test_result_error_custom_code():
    r = Result.error("未授权", code=401)
    assert r.code == 401


def test_page_result():
    p = PageResult(total=2, page=1, size=10, records=[{"a": 1}, {"b": 2}])
    assert p.total == 2
    assert p.page == 1
    assert p.size == 10
    assert len(p.records) == 2
