"""PromptTemplateManager - 版本化 + 激活 + 回滚 + 渲染（ADR-0005）。

- 逻辑身份 = type；每行 = 一个版本；每 type 恰一 is_active=true（DB partial unique 兜底）。
- 编辑 = 新增版本（version=max+1）并激活（先 deactivate 同 type 其他）。
- 回滚 = activate 旧版本。
- 渲染 = {{占位符}} 替换。
"""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PromptType
from app.core.exceptions import BusinessException
from app.models import PromptTemplate


class PromptTemplateManager:
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
        t = self._type_value(type_)
        max_v = await self.session.scalar(
            select(func.max(PromptTemplate.version)).where(PromptTemplate.type == t)
        ) or 0
        # 先 deactivate 同 type 其他激活（partial unique 要求每 type 恰一 active）
        await self.session.execute(
            update(PromptTemplate)
            .where(PromptTemplate.type == t, PromptTemplate.is_active.is_(True))
            .values(is_active=False)
        )
        tpl = PromptTemplate(
            type=t,
            version=max_v + 1,
            name=name,
            role_setting=role_setting,
            template_body=template_body,
            review_dimensions=review_dimensions,
            severity_levels=severity_levels,
            is_active=True,
        )
        self.session.add(tpl)
        await self.session.flush()
        await self.session.refresh(tpl)
        return tpl

    async def activate(self, template_id: int) -> PromptTemplate:
        """激活某个旧版本（回滚）：deactivate 同 type 其他 + 置本条 active。"""
        tpl = await self.session.get(PromptTemplate, template_id)
        if tpl is None:
            raise BusinessException(f"Prompt 模板 {template_id} 不存在")
        await self.session.execute(
            update(PromptTemplate)
            .where(
                PromptTemplate.type == tpl.type,
                PromptTemplate.is_active.is_(True),
                PromptTemplate.id != template_id,
            )
            .values(is_active=False)
        )
        tpl.is_active = True
        await self.session.flush()
        return tpl

    def render(self, template: PromptTemplate, params: dict[str, str] | None) -> str:
        body = template.template_body
        for k, v in (params or {}).items():
            body = body.replace("{{" + k + "}}", v)
        return body

    def render_system_prompt(self, template: PromptTemplate, params: dict[str, str] | None) -> str:
        return f"{template.role_setting}\n\n{self.render(template, params)}"
