"""TestFrame CLI - 统一命令入口"""

import click
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@click.group()
@click.version_option(version="0.1.0", prog_name="TestFrame")
def cli():
    """TestFrame - 通用自动化Bug发现体系

    基于成熟工具组合的自动化质量保障平台。
    覆盖 Android / 微信小程序 / H5 / 后端API / 云真机兼容性。
    """
    pass


@cli.command()
@click.option("--project", "-p", required=True, help="项目名称 (对应 config/projects/<name>.yaml)")
@click.option("--profile", "-P", default="smoke", help="执行策略 (smoke/regression/compatibility)")
@click.option("--device", "-d", default=None, help="指定设备ID")
@click.option("--env", "-e", default="staging", help="目标环境")
@click.option("--dry-run", is_flag=True, help="仅打印执行计划不实际执行")
def run(project, profile, device, env, dry_run):
    """执行测试流水线"""
    from orchestrator.engine import Orchestrator

    orch = Orchestrator(
        project_name=project,
        profile_name=profile,
        device=device,
        environment=env,
    )

    if dry_run:
        orch.print_plan()
        return

    success = orch.run()
    if not success:
        click.echo("[FAIL] Test pipeline failed", err=True)
        sys.exit(1)
    click.echo("[OK] Test pipeline completed")


@cli.command()
@click.option("--project", "-p", required=True, help="项目名称")
@click.option("--date", "-d", default=None, help="报告日期 (YYYY-MM-DD), 默认最新")
@click.option("--output", "-o", default=None, help="输出目录")
def report(project, date, output):
    """生成Allure报告"""
    from aggregator.collector import collect_and_generate

    report_path = collect_and_generate(project, date, output)
    click.echo(f"[OK] Report generated: {report_path}")


@cli.command()
@click.option("--project", "-p", required=True, help="项目名称")
@click.option("--build-id", "-b", default=None, help="构建ID")
def watch(project, build_id):
    """监控构建状态 (崩溃/错误)"""
    from evidence.collector import EvidenceCollector

    collector = EvidenceCollector(project)
    evidence = collector.collect(build_id)
    click.echo(evidence.summary())


@cli.command()
@click.option("--project", "-p", required=True, help="项目名称")
def check(project):
    """检查配置和运行环境"""
    from config_loader import load_config, validate_config

    try:
        config = load_config(project)
        errors = validate_config(config)
        if errors:
            click.echo("[FAIL] Config check failed:")
            for e in errors:
                click.echo(f"  - {e}")
            sys.exit(1)
        click.echo("[OK] Config check passed")
    except FileNotFoundError as e:
        click.echo(f"[FAIL] Config file not found: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--project", "-p", required=True, help="项目名称")
@click.option("--results-dir", "-r", default=None, help="测试结果目录")
def attribute(project, results_dir):
    """对失败用例进行缺陷归因"""
    from attribution.engine import AttributionEngine

    engine = AttributionEngine()
    report = engine.generate_report(project, results_dir)
    click.echo(report)


if __name__ == "__main__":
    cli()
