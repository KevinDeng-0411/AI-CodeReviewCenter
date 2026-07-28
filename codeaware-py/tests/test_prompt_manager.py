"""P3-1：PromptTemplateManager 版本化/激活/回滚/渲染（ADR-0005）。"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.ai.prompt.template_manager import PromptTemplateManager
from app.core.enums import PromptType
from app.models import PromptTemplate


@pytest.fixture
def pm(db_session):
    return PromptTemplateManager(db_session)


async def test_save_and_activate_and_get(pm):
    tpl = await pm.save_and_activate(
        PromptType.CODE_REVIEW, name="v1", role_setting="role", template_body="body {{source_code}}"
    )
    assert tpl.version == 1
    assert tpl.is_active is True
    got = await pm.get_active(PromptType.CODE_REVIEW)
    assert got is not None and got.id == tpl.id


async def test_activation_invariant_only_one_active(pm):
    v1 = await pm.save_and_activate(PromptType.CODE_REVIEW, name="v1", role_setting="r", template_body="b1")
    v2 = await pm.save_and_activate(PromptType.CODE_REVIEW, name="v2", role_setting="r", template_body="b2")
    assert v2.version == 2

    active = await pm.get_active(PromptType.CODE_REVIEW)
    assert active.id == v2.id  # v2 激活
    v1_refresh = await pm.session.get(PromptTemplate, v1.id)
    assert v1_refresh.is_active is False  # v1 自动 deactivate


async def test_rollback_via_activate(pm):
    v1 = await pm.save_and_activate(PromptType.CODE_REVIEW, name="v1", role_setting="r", template_body="b1")
    v2 = await pm.save_and_activate(PromptType.CODE_REVIEW, name="v2", role_setting="r", template_body="b2")
    await pm.activate(v1.id)  # 回滚到 v1

    active = await pm.get_active(PromptType.CODE_REVIEW)
    assert active.id == v1.id


async def test_render_and_system_prompt(pm):
    tpl = await pm.save_and_activate(
        PromptType.CODE_REVIEW, name="v1", role_setting="ROLE", template_body="Hello {{source_code}}!"
    )
    assert pm.render(tpl, {"source_code": "X"}) == "Hello X!"
    assert pm.render_system_prompt(tpl, {"source_code": "X"}) == "ROLE\n\nHello X!"


async def test_list_by_type_orders_by_version_desc(pm):
    await pm.save_and_activate(PromptType.CODE_REVIEW, name="v1", role_setting="r", template_body="b1")
    await pm.save_and_activate(PromptType.CODE_REVIEW, name="v2", role_setting="r", template_body="b2")
    versions = await pm.list_by_type(PromptType.CODE_REVIEW)
    assert [t.version for t in versions] == [2, 1]


async def test_partial_unique_blocks_two_active(db_session):
    """DB 层 partial unique 约束：同 type 不先 deactivate 直接插第二个 active -> IntegrityError。"""
    db_session.add(
        PromptTemplate(type="CODE_REVIEW", version=1, name="a", role_setting="r", template_body="b", is_active=True)
    )
    await db_session.flush()
    db_session.add(
        PromptTemplate(type="CODE_REVIEW", version=2, name="b", role_setting="r", template_body="b", is_active=True)
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
