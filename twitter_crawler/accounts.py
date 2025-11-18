from __future__ import annotations

from typing import List, Optional
from rapidfuzz import fuzz
from rich.prompt import Prompt, Confirm
from rich import print as rprint

from .data_prep import normalize_company_name
from .twitter_api import TwitterAPI
from .storage import AccountInfo


def choose_one_account_interactive(company_norm: str, candidates: List[dict]) -> Optional[AccountInfo]:
    """
    多个候选账号时的 CLI 交互选择
    """
    if not candidates:
        return None
    rprint(f"[bold yellow]公司：[/bold yellow]{company_norm} 发现多个候选账号：")
    for idx, u in enumerate(candidates, start=1):
        rprint(f"{idx}. @{u.get('username')} | {u.get('name')} | verified={u.get('verified')} | followers={u.get('public_metrics',{}).get('followers_count')}")
    choice = Prompt.ask("选择序号（回车跳过）", default="")
    if not choice.strip().isdigit():
        return None
    n = int(choice)
    if n < 1 or n > len(candidates):
        return None
    u = candidates[n - 1]
    return AccountInfo(
        company_normalized=company_norm,
        twitter_id=u.get("id"),
        username=u.get("username"),
        name=u.get("name"),
        verified=u.get("verified"),
    )


def search_account_for_company(api: TwitterAPI, company_name: str, prefer_verified: bool = True) -> Optional[AccountInfo]:
    """
    通过公司名查找最合适的账号：
    - 先尝试直接用户名同名
    - 再使用推文搜索近似用户（includes.users）
    - verified 优先，其次使用模糊匹配度
    """
    norm = normalize_company_name(company_name)

    # 1) 直接按用户名尝试
    direct = api.get_user_by_username(norm.title().replace(" ", ""))
    candidates: List[dict] = []
    if direct:
        candidates.append(direct)

    # 2) 近似搜索（基于推文 includes.users）
    users = api.search_users_by_query(norm)
    for u in users:
        if not any(u.get("id") == c.get("id") for c in candidates):
            candidates.append(u)

    if not candidates:
        return None

    # 评分：verified 优先，名称/用户名与公司名的相似度
    def score(u: dict) -> tuple:
        verified_bonus = 100 if prefer_verified and u.get("verified") else 0
        name_score = fuzz.token_set_ratio(norm, (u.get("name") or "").upper())
        uname_score = fuzz.token_set_ratio(norm, (u.get("username") or "").upper())
        return (verified_bonus, name_score, uname_score, u.get("public_metrics", {}).get("followers_count", 0))

    candidates.sort(key=score, reverse=True)

    # 如果前几名分值接近，要求人工确认
    top = candidates[:3]
    if len(top) > 1:
        need_confirm = Confirm.ask("检测到多个相近账号，是否手动选择？", default=True)
        if need_confirm:
            chosen = choose_one_account_interactive(norm, top)
            return chosen

    u0 = candidates[0]
    return AccountInfo(
        company_normalized=norm,
        twitter_id=u0.get("id"),
        username=u0.get("username"),
        name=u0.get("name"),
        verified=u0.get("verified"),
    )



