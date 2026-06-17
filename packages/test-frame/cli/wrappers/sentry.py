"""Sentry wrapper — 通过API查询崩溃和性能数据"""

import requests
import os
from datetime import datetime


def fetch_issues(project_config: dict, build_id: str = None) -> list[dict]:
    """从Sentry API获取指定版本的Issue列表"""
    sentry_config = project_config.get("sentry", {})
    auth_token = sentry_config.get("auth_token", os.environ.get("SENTRY_AUTH_TOKEN", ""))
    org = sentry_config.get("org", "")
    project_slug = sentry_config.get("project", "")
    base_url = sentry_config.get("base_url", "https://sentry.io")

    if not auth_token or not org or not project_slug:
        print("    [WARN] Sentry配置不完整，跳过")
        return []

    params = {
        "statsPeriod": "14d",
        "limit": 100,
    }
    if build_id:
        params["query"] = f"release:{build_id}"

    try:
        resp = requests.get(
            f"{base_url}/api/0/projects/{org}/{project_slug}/issues/",
            headers={"Authorization": f"Bearer {auth_token}"},
            params=params,
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        print("    [WARN] Sentry API不可达")
        return []
    except Exception as e:
        print(f"    [WARN] Sentry查询异常: {e}")
        return []


def get_crash_summary(project_config: dict, build_id: str = None) -> dict:
    """获取崩溃摘要"""
    issues = fetch_issues(project_config, build_id)
    unresolved = [i for i in issues if i.get("status") == "unresolved"]

    return {
        "total_issues": len(issues),
        "unresolved": len(unresolved),
        "by_severity": _count_by(issues, "level"),
        "top_issues": [
            {
                "title": i.get("title"),
                "count": i.get("count"),
                "first_seen": i.get("firstSeen"),
                "last_seen": i.get("lastSeen"),
            }
            for i in unresolved[:5]
        ],
    }


def _count_by(items: list, key: str) -> dict:
    counts = {}
    for item in items:
        val = item.get(key, "unknown")
        counts[val] = counts.get(val, 0) + 1
    return counts
