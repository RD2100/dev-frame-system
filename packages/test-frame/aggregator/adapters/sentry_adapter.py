"""Sentry结果适配器 — Issue API → 统一TestResult格式"""

import os
import requests


def collect(project_config: dict = None) -> list[dict]:
    """从Sentry API收集崩溃数据，转为统一格式"""
    if project_config is None:
        return []

    sentry_config = project_config.get("sentry", {})
    auth_token = sentry_config.get("auth_token", os.environ.get("SENTRY_AUTH_TOKEN", ""))
    org = sentry_config.get("org", "")
    project_slug = sentry_config.get("project", "")
    base_url = sentry_config.get("base_url", "https://sentry.io")

    if not auth_token or not org or not project_slug:
        return []

    try:
        resp = requests.get(
            f"{base_url}/api/0/projects/{org}/{project_slug}/issues/",
            headers={"Authorization": f"Bearer {auth_token}"},
            params={"statsPeriod": "14d", "limit": 100, "query": "is:unresolved"},
            timeout=30
        )
        resp.raise_for_status()
        issues = resp.json()
    except Exception:
        return []

    results = []
    for issue in issues:
        results.append({
            "test_name": f"[Sentry] {issue.get('title', 'unknown')}",
            "status": "failed",  # Sentry issues are always failures
            "tool": "sentry",
            "error": {
                "message": issue.get("metadata", {}).get("value", issue.get("title", "")),
                "stack_trace": issue.get("metadata", {}).get("value", ""),
            },
            "metadata": {
                "issue_id": issue.get("id"),
                "count": issue.get("count", 1),
                "level": issue.get("level", "error"),
                "first_seen": issue.get("firstSeen", ""),
                "last_seen": issue.get("lastSeen", ""),
                "status": issue.get("status", "unresolved"),
            },
        })
    return results
