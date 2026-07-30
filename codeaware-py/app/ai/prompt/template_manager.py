"""PromptTemplateManager - 版本化 + 激活 + 回滚 + 渲染（ADR-0005）。

- 逻辑身份 = type；每行 = 一个版本；每 type 恰一 is_active=true（DB partial unique 兜底）。
- 编辑 = 新增版本（version=max+1）并激活（先 deactivate 同 type 其他）。
- 回滚 = activate 旧版本。
- 渲染 = {{占位符}} 替换。
"""

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PromptType
from app.core.exceptions import BusinessException
from app.models import PromptTemplate


class PromptTemplateManager:
    _VERSION_WRITE_ATTEMPTS = 2

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _type_value(type_) -> str:
        return type_.value if isinstance(type_, PromptType) else type_

    async def get_active(self, type_) -> PromptTemplate | None:
        t = self._type_value(type_)
        return await self.session.scalar(
            select(PromptTemplate).where(
                PromptTemplate.type == t,
                PromptTemplate.is_active.is_(True),
            )
        )

    async def get_by_id_for_type(self, template_id: int, type_) -> PromptTemplate | None:
        t = self._type_value(type_)
        return await self.session.scalar(
            select(PromptTemplate).where(
                PromptTemplate.id == template_id,
                PromptTemplate.type == t,
            )
        )

    async def _lock_type(self, type_) -> str:
        t = self._type_value(type_)
        await self.session.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended('prompt-template:' || :type, 0))"
            ),
            {"type": t},
        )
        return t

    async def list_by_type(self, type_) -> list[PromptTemplate]:
        t = self._type_value(type_)
        r = await self.session.execute(
            select(PromptTemplate)
            .where(PromptTemplate.type == t)
            .order_by(PromptTemplate.version.desc())
        )
        return list(r.scalars().all())

    async def save_and_activate(
        self,
        type_,
        *,
        name: str,
        role_setting: str,
        template_body: str,
        review_dimensions: str | None = None,
        severity_levels: str | None = None,
    ) -> PromptTemplate:
        """新增版本并激活：先 deactivate 同 type 其他 -> insert 新 active（version=max+1）。"""
        t = await self._lock_type(type_)
        for attempt in range(self._VERSION_WRITE_ATTEMPTS):
            try:
                # savepoint 让极少数约束竞争可在同一请求事务中安全重试；
                # type advisory lock 仍是正常并发路径的串行化边界。
                async with self.session.begin_nested():
                    max_v = await self.session.scalar(
                        select(func.max(PromptTemplate.version)).where(
                            PromptTemplate.type == t
                        )
                    ) or 0
                    # 新行先 inactive 落库，避免与当前 active 冲突；随后原子切换。
                    tpl = PromptTemplate(
                        type=t,
                        version=max_v + 1,
                        name=name,
                        role_setting=role_setting,
                        template_body=template_body,
                        review_dimensions=review_dimensions,
                        severity_levels=severity_levels,
                        is_active=False,
                    )
                    self.session.add(tpl)
                    await self.session.flush()
                    await self.session.execute(
                        update(PromptTemplate)
                        .where(
                            PromptTemplate.type == t,
                            PromptTemplate.is_active.is_(True),
                        )
                        .values(is_active=False)
                    )
                    tpl.is_active = True
                    await self.session.flush()
                await self.session.refresh(tpl)
                return tpl
            except IntegrityError as exc:
                if attempt + 1 >= self._VERSION_WRITE_ATTEMPTS:
                    raise BusinessException(
                        "PROMPT_VERSION_CONFLICT",
                        status_code=409,
                    ) from exc
        raise AssertionError("unreachable prompt version retry state")

    async def activate(self, template_id: int) -> PromptTemplate:
        """激活某个旧版本（回滚）：deactivate 同 type 其他 + 置本条 active。"""
        template_type = await self.session.scalar(
            select(PromptTemplate.type).where(PromptTemplate.id == template_id)
        )
        if template_type is None:
            raise BusinessException("PROMPT_NOT_FOUND", status_code=404)
        await self._lock_type(template_type)
        await self.session.execute(
            update(PromptTemplate)
            .where(
                PromptTemplate.type == template_type,
                PromptTemplate.is_active.is_(True),
                PromptTemplate.id != template_id,
            )
            .values(is_active=False)
        )
        # 显式 UPDATE，避免并发等待锁期间 identity map 中的旧 is_active=True
        # 被 SQLAlchemy 误判为“无需写入”，造成同 type 暂时没有 active。
        await self.session.execute(
            update(PromptTemplate)
            .where(PromptTemplate.id == template_id)
            .values(is_active=True)
        )
        await self.session.flush()
        tpl = await self.session.scalar(
            select(PromptTemplate)
            .where(PromptTemplate.id == template_id)
            .execution_options(populate_existing=True)
        )
        if tpl is None:  # pragma: no cover - 同一事务内目标不会消失
            raise BusinessException("PROMPT_NOT_FOUND", status_code=404)
        return tpl

    def render(self, template: PromptTemplate, params: dict[str, str] | None) -> str:
        body = template.template_body
        for k, v in (params or {}).items():
            body = body.replace("{{" + k + "}}", v)
        return body

    def render_system_prompt(self, template: PromptTemplate, params: dict[str, str] | None) -> str:
        return f"{template.role_setting}\n\n{self.render(template, params)}"
