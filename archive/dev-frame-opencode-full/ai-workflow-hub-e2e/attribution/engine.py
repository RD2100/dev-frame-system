"""缺陷归因引擎 v2 — 指纹追踪 + 频率统计 + 模式匹配

升级能力:
1. 失败指纹(hash) — test_name + error_type → 唯一标识
2. 状态分类 — NEW / RECURRING / FLAKY(连续3次+) / RESOLVED
3. 频率追踪 — 每次运行记录，跨时间对比
4. 正则规则 — 保留原有20条规则做根因匹配
"""

import os, re, json, hashlib, yaml
from pathlib import Path
from datetime import datetime
from collections import defaultdict

HISTORY_FILE = "reports/failure_history.json"


class FingerprintDB:
    """失败指纹数据库 — 轻量JSON文件存储"""

    def __init__(self, path=HISTORY_FILE):
        self.path = path
        self.db = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"records": {}, "runs": []}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.db, f, ensure_ascii=False, indent=2)

    def fingerprint(self, test_name, error_msg):
        """生成失败指纹: sha256(test_name + error关键词)"""
        keywords = self._extract_keywords(error_msg)
        raw = f"{test_name}|{keywords}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _extract_keywords(self, msg):
        """从错误消息中提取关键词（去变量值）"""
        if not msg:
            return "unknown"
        # 去掉数字、时间戳、UUID等变量
        cleaned = re.sub(r'\d+', 'N', msg)
        cleaned = re.sub(r'0x[0-9a-f]+', 'HEX', cleaned)
        cleaned = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', 'UUID', cleaned)
        return cleaned[:200]

    def record(self, fp, test_name, status, error_msg, tool="unknown"):
        """记录一次失败"""
        if fp not in self.db["records"]:
            self.db["records"][fp] = {
                "fp": fp,
                "test_name": test_name,
                "tool": tool,
                "first_seen": datetime.now().isoformat(),
                "last_seen": datetime.now().isoformat(),
                "count": 0,
                "consecutive": 0,
                "history": [],  # [{time, status}]
                "resolved": False,
            }
        rec = self.db["records"][fp]
        rec["last_seen"] = datetime.now().isoformat()
        rec["count"] += 1
        rec["history"].append({
            "time": datetime.now().isoformat(),
            "status": status,
            "error": error_msg[:300] if error_msg else "",
        })
        # 保持最近50条
        if len(rec["history"]) > 50:
            rec["history"] = rec["history"][-50:]

        # 计算连续次数
        consecutive = 0
        for h in reversed(rec["history"]):
            if h["status"] in ("failed", "broken"):
                consecutive += 1
            else:
                break
        rec["consecutive"] = consecutive

    def classify(self, fp):
        """分类: NEW / RECURRING / FLAKY / RESOLVED"""
        rec = self.db["records"].get(fp)
        if not rec:
            return "NEW"
        if rec.get("resolved"):
            return "RESOLVED"
        if rec.get("consecutive", 0) >= 3:
            return "FLAKY"
        if rec.get("count", 0) >= 2:
            return "RECURRING"
        return "NEW"

    def resolve(self, fp):
        """标记为已修复"""
        if fp in self.db["records"]:
            self.db["records"][fp]["resolved"] = True
            self.db["records"][fp]["resolved_at"] = datetime.now().isoformat()

    def start_run(self, run_id=None):
        """开始一次新的运行"""
        run = {
            "id": run_id or datetime.now().strftime("%Y%m%d-%H%M%S"),
            "time": datetime.now().isoformat(),
            "failures": [],
        }
        self.db["runs"].append(run)
        # 保留最近100次运行
        if len(self.db["runs"]) > 100:
            self.db["runs"] = self.db["runs"][-100:]
        return run

    def stats(self):
        """统计概览"""
        records = self.db["records"]
        total = len(records)
        new = sum(1 for r in records.values() if self.classify(r["fp"]) == "NEW")
        recurring = sum(1 for r in records.values() if self.classify(r["fp"]) == "RECURRING")
        flaky = sum(1 for r in records.values() if self.classify(r["fp"]) == "FLAKY")
        resolved = sum(1 for r in records.values() if r.get("resolved"))
        return {
            "total_patterns": total,
            "new": new, "recurring": recurring,
            "flaky": flaky, "resolved": resolved,
        }


class AttributionEngine:
    """归因引擎 v2 — 指纹追踪 + 规则匹配"""

    def __init__(self, rules_dir="attribution/rules/"):
        self.rules = self._load_rules(rules_dir)
        self.fpdb = FingerprintDB()

    def _load_rules(self, rules_dir):
        rules = []
        rules_path = Path(rules_dir)
        if not rules_path.exists():
            return rules
        for f in rules_path.glob("*.yaml"):
            try:
                with open(f, encoding='utf-8') as fh:
                    data = yaml.safe_load(fh)
                if data and "rules" in data:
                    rules.extend(data["rules"])
            except Exception:
                continue
        return rules

    def attribute(self, test_result: dict) -> dict:
        """对单个失败用例进行归因分析（v2增强）"""
        test_name = test_result.get("test_name", "unknown")
        tool = test_result.get("tool", "unknown")
        error_msg = ""
        if test_result.get("error"):
            error_msg = test_result["error"].get("message", "")

        # 1. 生成指纹
        fp = self.fpdb.fingerprint(test_name, error_msg)

        # 2. 记录到指纹库
        self.fpdb.record(fp, test_name, test_result.get("status", "failed"), error_msg, tool)

        # 3. 分类
        category = self.fpdb.classify(fp)
        fp_rec = self.fpdb.db["records"].get(fp, {})

        # 4. 规则匹配
        matched_rule, attribution = self._match_rules(error_msg, test_result)

        return {
            "test_name": test_name,
            "fingerprint": fp,
            "category": category,
            "occurrence_count": fp_rec.get("count", 1),
            "consecutive": fp_rec.get("consecutive", 1),
            "first_seen": fp_rec.get("first_seen", ""),
            "last_seen": fp_rec.get("last_seen", ""),
            "matched_rule": matched_rule,
            "root_cause": attribution.get("root_cause", "未知"),
            "likely_module": attribution.get("likely_module", test_result.get("tool", "未知")),
            "severity": attribution.get("severity", "P3"),
            "suggestion": attribution.get("suggestion", "人工分析"),
            "tool": tool,
        }

    def _match_rules(self, error_msg, test_result):
        """正则规则匹配"""
        stack_trace = ""
        if test_result.get("error"):
            stack_trace = test_result["error"].get("stack_trace", "")

        text = f"{error_msg}\n{stack_trace}"

        for rule in self.rules:
            sources = rule.get("source", [])
            search_in = ""
            if "stacktrace" in sources:
                search_in += stack_trace
            if "error_message" in sources:
                search_in += error_msg
            if "logcat" in sources:
                search_in += text

            if re.search(rule["pattern"], search_in, re.IGNORECASE):
                return rule["id"], rule.get("attribution", {})

        return None, {"root_cause": "未匹配已知规则", "suggestion": "人工分析", "severity": "P3"}

    def attribute_batch(self, test_results: list) -> list:
        """批量归因"""
        self.fpdb.start_run()
        results = []
        for r in test_results:
            if r.get("status") in ("failed", "broken"):
                results.append(self.attribute(r))
        self.fpdb.save()
        return results

    def generate_report(self, project_name: str, results_dir=None) -> str:
        """生成归因报告（v2增强版）"""
        from aggregator.collector import collect_failed_results
        failed = collect_failed_results()
        attributed = self.attribute_batch(failed)

        # 按分类统计
        by_cat = defaultdict(list)
        for a in attributed:
            by_cat[a["category"]].append(a)

        stats = self.fpdb.stats()

        lines = [
            f"# 缺陷归因报告 — {project_name}",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 本次概览",
            f"- 失败用例: {len(attributed)}",
            f"- 新增失败 (NEW): {len(by_cat.get('NEW',[]))}",
            f"- 重复失败 (RECURRING): {len(by_cat.get('RECURRING',[]))}",
            f"- 不稳定失败 (FLAKY, ≥3次): {len(by_cat.get('FLAKY',[]))}",
            f"- 已修复 (RESOLVED): {len(by_cat.get('RESOLVED',[]))}",
            f"- 规则匹配: {sum(1 for a in attributed if a.get('matched_rule'))}",
            "",
            "## 历史统计",
            f"- 历史模式总数: {stats['total_patterns']}",
            f"- 已修复: {stats['resolved']}",
            f"- 活跃FLAKY: {stats['flaky']}",
            "",
        ]

        for cat in ["FLAKY", "RECURRING", "NEW"]:
            items = by_cat.get(cat, [])
            if not items:
                continue
            lines.append(f"## {cat} 失败 ({len(items)}条)")
            lines.append("")
            lines.append("| 用例 | 次数 | 严重级别 | 根因 | 建议 |")
            lines.append("|------|------|---------|------|------|")
            for a in items[:10]:
                lines.append(
                    f"| {a['test_name'][:30]} | ×{a['occurrence_count']} "
                    f"| {a['severity']} | {a['root_cause'][:20]} | {a['suggestion'][:30]} |"
                )
            lines.append("")

        # Top 10 高频失败
        top = sorted(attributed, key=lambda a: a["occurrence_count"], reverse=True)[:10]
        if top and top[0]["occurrence_count"] > 1:
            lines.append("## Top 高频失败")
            lines.append("")
            for i, a in enumerate(top, 1):
                lines.append(f"{i}. **{a['test_name'][:50]}** — ×{a['occurrence_count']} — {a['root_cause']}")

        report = "\n".join(lines)

        output_dir = os.path.join("attribution", "output")
        os.makedirs(output_dir, exist_ok=True)
        report_path = os.path.join(output_dir, f"{project_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"  Attribution report: {report_path}")
        return report

    def resolve_fingerprint(self, test_name, error_msg):
        """手动标记某个失败模式为已修复"""
        fp = self.fpdb.fingerprint(test_name, error_msg)
        self.fpdb.resolve(fp)
        self.fpdb.save()
        return fp
