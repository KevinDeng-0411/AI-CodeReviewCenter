"""引导创建首个 admin 账号（团队化升级阶段 A）。

首次部署时运行一次：python -m scripts.create_admin
之后用 POST /api/auth/register（admin 鉴权）建其余账号。
"""

import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models import User


async def main() -> None:
    username = input("username: ").strip()
    if not username:
        print("username 不能为空", file=sys.stderr)
        sys.exit(1)
    password = getpass.getpass("password: ")
    if len(password) < 6:
        print("password 至少 6 位", file=sys.stderr)
        sys.exit(1)
    display_name = input("display_name (可选): ").strip() or None

    async with AsyncSessionLocal() as session:
        exists = await session.scalar(select(User.id).where(User.username == username))
        if exists is not None:
            print(f"用户 {username} 已存在", file=sys.stderr)
            sys.exit(1)
        user = User(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            display_name=display_name,
        )
        session.add(user)
        await session.commit()
        print(f"已创建 admin 账号: {username} (id={user.id})")


if __name__ == "__main__":
    asyncio.run(main())
