"""认证与用户上下文。

- API Key：设置 TAGRAG_API_KEYS 后，所有 /api 请求需携带 `X-API-Key`
- 用户身份/用户组：由上游网关（SSO/OA）注入 `X-User-Id`、`X-User-Groups`（逗号分隔），
  用于文档级 ACL 过滤。直接对外暴露服务时，务必在网关层剥离客户端自带的这两个头。
- Agent 调用时带 `X-Agent-Id`，日志中记为 agent:<id>；Agent 的权限同样由用户组决定（最小权限）
- 带 admin 组（或未开启 API Key 的开发模式）的调用方可绕过 ACL。
"""
from dataclasses import dataclass
from typing import List, Optional

from fastapi import Header, HTTPException

from .config import get_settings

ADMIN_GROUP = "admin"


@dataclass
class UserContext:
    user_id: Optional[str]
    groups: Optional[List[str]]  # None = 不做 ACL 过滤
    agent_id: Optional[str] = None  # 以 Agent 身份调用时（如 MCP），用于审计

    @property
    def actor(self) -> Optional[str]:
        return f"agent:{self.agent_id}" if self.agent_id else self.user_id

    @property
    def is_admin(self) -> bool:
        return self.groups is None or ADMIN_GROUP in self.groups


def get_user(x_api_key: Optional[str] = Header(default=None),
             x_user_id: Optional[str] = Header(default=None),
             x_user_groups: Optional[str] = Header(default=None),
             x_agent_id: Optional[str] = Header(default=None)) -> UserContext:
    s = get_settings()
    keys = s.api_key_set
    if keys and x_api_key not in keys:
        raise HTTPException(status_code=401, detail="无效的 API Key")
    if x_user_groups is None:
        # 开发模式（未配置 key）不限制；生产模式未声明用户组则只能看公开文档
        groups = None if not keys else []
    else:
        groups = [g.strip() for g in x_user_groups.split(",") if g.strip()]
    return UserContext(user_id=x_user_id, groups=groups, agent_id=x_agent_id)


def acl_groups_for(user: UserContext) -> Optional[List[str]]:
    return None if user.is_admin else (user.groups or [])


def require_admin(user: UserContext) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
