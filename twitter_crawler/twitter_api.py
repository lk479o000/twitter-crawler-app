from __future__ import annotations

import time
from typing import Dict, Iterable, List, Optional, Tuple
import requests

from .config import Settings, get_settings


BASE_URL = "https://api.x.com/2"


class TwitterAPI:
    """
    轻量封装 Twitter API v2（X）
    仅覆盖本项目所需的用户查找与推文搜索。
    """

    def __init__(self, bearer_token: Optional[str] = None, settings: Optional[Settings] = None):
        settings = settings or get_settings()
        self.settings = settings
        self.bearer_token = bearer_token or settings.twitter_bearer_token
        self.use_search_all = settings.use_search_all
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.bearer_token}"})
        # 简单的节流：按 requests_per_minute 计算最小请求间隔
        self._min_interval = 60.0 / max(1, settings.requests_per_minute)
        self._last_request_ts = 0.0

    def _respect_rpm(self):
        now = time.time()
        elapsed = now - self._last_request_ts
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_ts = time.time()

    def _get(self, path: str, params: Dict) -> Dict:
        url = f"{BASE_URL}{path}"
        # 带指数退避的重试
        for attempt in range(self.settings.rate_limit_max_retries):
            self._respect_rpm()
            resp = self.session.get(url, params=params, timeout=30)
            
            # 处理不应该重试的错误（如认证失败、资源不存在等）
            if resp.status_code in [401, 403, 404, 406, 410]:
                # 401: 认证失败 - 不应该重试
                # 403: 权限不足 - 不应该重试
                # 404: 资源不存在 - 不应该重试
                # 406: 不接受的格式 - 不应该重试
                # 410: 资源已删除 - 不应该重试
                resp.raise_for_status()
            
            # 处理服务器端错误和其他可重试错误
            elif resp.status_code == 429:
                # 429: 速率限制 - 应该进行指数退避重试
                delay = min(self.settings.rate_limit_base_delay_seconds * (2 ** attempt), self.settings.rate_limit_max_delay_seconds)
                time.sleep(delay)
                continue
            elif 500 <= resp.status_code < 600:
                # 服务器端错误 - 可以尝试重试
                delay = min(self.settings.rate_limit_base_delay_seconds * (2 ** attempt), self.settings.rate_limit_max_delay_seconds)
                time.sleep(delay)
                continue
            
            # 成功响应或其他不应重试的客户端错误
            resp.raise_for_status()
            return resp.json()
        
        # 所有重试都失败后，如果最后一次响应是429，提供更详细的错误信息
        if resp.status_code == 429:
            raise Exception(f"Twitter API 速率限制错误 (429)：已达到最大重试次数 {self.settings.rate_limit_max_retries} 次。请检查API密钥和使用情况。")
        
        # 其他错误直接抛出
        resp.raise_for_status()
        return {}

    # 用户查找
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        data = self._get(
            "/users/by/username/{}".format(username),
            params={"user.fields": "id,name,username,verified,description,public_metrics,created_at"},
        )
        return data.get("data")

    def search_users_by_query(self, query: str, max_results: int = 10) -> List[Dict]:
        # X API 没有官方“用户搜索”端点公开；实践中常用 via recent tweets + expansions 提取用户
        # 这里用 recent search 作为近似方案
        tweets = self.search_tweets(
            query=query, max_results=50, expansions=["author_id"], tweet_fields="author_id,public_metrics"
        )
        users = tweets.get("includes", {}).get("users", [])
        # 去重
        seen = set()
        unique = []
        for u in users:
            if u["id"] in seen:
                continue
            seen.add(u["id"])
            unique.append(u)
            if len(unique) >= max_results:
                break
        return unique

    # 推文搜索
    def search_tweets(
        self,
        query: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        max_results: int = 100,
        next_token: Optional[str] = None,
        expansions: Optional[Iterable[str]] = None,
        tweet_fields: str = "id,text,created_at,public_metrics,author_id",
        user_fields: str = "id,name,username,verified,public_metrics,created_at",
    ) -> Dict:
        path = "/tweets/search/all" if self.use_search_all else "/tweets/search/recent"
        params: Dict[str, str] = {
            "query": query,
            "max_results": str(max(10, min(max_results, 100))),
            "tweet.fields": tweet_fields,
            "user.fields": user_fields,
        }
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        if expansions:
            params["expansions"] = ",".join(expansions)
        if next_token:
            params["next_token"] = next_token
        return self._get(path, params)


