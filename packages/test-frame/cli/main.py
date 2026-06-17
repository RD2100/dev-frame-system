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
@click.option("--require-html", is_flag=True, help="Fail when Allure HTML cannot be generated")
def report(project, date, output, require_html):
    """生成Allure报告"""
    from aggregator.collector import collect_and_generate

    result = collect_and_generate(project, date, output)
    if result.status == "PASS":
        click.echo(f"[OK] Allure HTML generated: {result.html_path}")
        return
    if result.status == "BLOCKED":
        click.echo(f"[BLOCKED] Allure HTML not generated: {result.reason}")
        click.echo(f"[OK] Fallback manifest written: {result.manifest_path}")
        if require_html:
            sys.exit(1)
        return

    click.echo(f"[FAIL] Allure HTML generation failed: {result.reason}", err=True)
    click.echo(f"[FAIL] Manifest written: {result.manifest_path}", err=True)
    sys.exit(1)


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
@click.option("--project", "-p", required=False, help="项目名称")
@click.option("--capability", "capability_name", default=None, help="Capability to probe, or 'all'")
@click.option("--profile", "capability_profile", default=None, help="Capability profile to probe")
@click.option("--required", multiple=True, help="Capability that must PASS")
@click.option("--evidence", default=None, help="Write capability evidence JSON to this path")
def check(project, capability_name, capability_profile, required, evidence):
    """检查配置和运行环境"""
    if capability_name or capability_profile:
        from capability.profiles import resolve_profile
        from capability.probe import required_gate_failed, run_probes, write_evidence

        try:
            names = []
            required_names = list(required)
            if capability_profile:
                profile_names = resolve_profile(capability_profile)
                names.extend(profile_names)
                required_names.extend(profile_names)
            if capability_name:
                names.extend(name.strip() for name in capability_name.split(",") if name.strip())
            results = run_probes(names, required=required_names)
        except ValueError as e:
            click.echo(f"[FAIL] {e}", err=True)
            sys.exit(1)

        if capability_profile:
            click.echo(f"[PROFILE] {capability_profile}: required {', '.join(resolve_profile(capability_profile))}")
        for result in results:
            suffix = f" (reason_code={result.reason_code})" if result.reason_code else ""
            click.echo(f"[{result.status}] {result.capability}: {result.reason}{suffix}")

        if evidence:
            output_path = write_evidence(
                results,
                evidence,
                profile_name=capability_profile,
                command_invoked=sys.argv[1:],
            )
            click.echo(f"[OK] Capability evidence written: {output_path}")

        if required_gate_failed(results):
            click.echo("[FAIL] Required capability check failed", err=True)
            sys.exit(1)

        click.echo("[OK] Capability check completed")
        return

    if not project:
        click.echo("[FAIL] --project is required unless --capability is provided", err=True)
        sys.exit(1)

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


@cli.group()
def evidence():
    """Evidence package utilities."""
    pass


@evidence.command("validate")
@click.option("--pack", required=True, help="Evidence ZIP package to validate")
def validate_evidence_pack(pack):
    """Validate module GPT evidence package shape."""
    from tools.validate_evidence_pack import validate_pack

    result = validate_pack(pack)
    status = "PASS" if result.passed else "FAILED"
    click.echo(f"[{status}] Evidence pack validation")
    if result.missing_required:
        click.echo(f"Missing required entries: {', '.join(result.missing_required)}")
    if not result.has_git_patch:
        click.echo("Missing git patch: git/show.patch or git/show-*.patch")
    if not result.raw_evidence_json:
        click.echo("Missing raw evidence JSON under evidence/")
    if result.violations:
        click.echo("Sensitive/local-path violations:")
        for violation in result.violations:
            click.echo(
                f"- {violation.file}:{violation.line} "
                f"[{violation.rule}] {violation.excerpt_redacted}"
            )
    for error in result.errors:
        click.echo(f"- {error}")
    if not result.passed:
        sys.exit(1)


@cli.group()
def authorization():
    """RuntimeAuthorization utilities."""
    pass


@authorization.command("validate")
@click.option("--file", "file_path", required=True, help="RuntimeAuthorization JSON file")
def validate_authorization(file_path):
    """Validate a RuntimeAuthorization request package."""
    from tools.validate_runtime_authorization import validate_authorization as validate_auth_file

    result = validate_auth_file(file_path)
    status = "PASS" if result.passed else "FAILED"
    click.echo(f"[{status}] RuntimeAuthorization validation")
    click.echo(f"authorization_type: {result.authorization_type}")
    click.echo(f"permits_real_e2e: {str(result.permits_real_e2e).lower()}")
    for error in result.errors:
        click.echo(f"- {error}")
    if not result.passed:
        sys.exit(1)


@cli.group()
def plan():
    """Dry execution plan utilities."""
    pass


@plan.command("miniapp-positive-pilot")
@click.option("--prereq-evidence", required=True, help="TGM MiniApp prerequisite evidence JSON")
@click.option("--out", required=True, help="Markdown plan path")
@click.option("--json-out", "json_out", required=True, help="JSON plan path")
def miniapp_positive_pilot_plan(prereq_evidence, out, json_out):
    """Generate a dry TGM MiniApp positive pilot execution plan."""
    from tools.generate_miniapp_positive_pilot_plan import generate_plan

    result = generate_plan(prereq_evidence, out, json_out)
    click.echo(f"plan_status: {result['plan_status']}")
    click.echo(f"primary_blocker: {result['prerequisite_summary']['primary_blocker']}")
    click.echo(f"permits_real_e2e: {str(result['permits_real_e2e']).lower()}")


@cli.group()
def pilot():
    """Pilot dry-run utilities."""
    pass


@pilot.command("miniapp-positive-pilot-dry-run")
@click.option("--plan", "plan_path", required=True, help="Positive pilot plan JSON")
@click.option("--out", required=True, help="Dry-run manifest JSON path")
def miniapp_positive_pilot_dry_run(plan_path, out):
    """Generate a dry execution manifest for a TGM MiniApp positive pilot plan."""
    from tools.run_miniapp_positive_pilot_dry import run_dry

    result = run_dry(plan_path, out)
    click.echo(f"final_dry_run_verdict: {result['final_dry_run_verdict']}")
    click.echo(f"executed_real_runtime: {str(result['executed_real_runtime']).lower()}")
    click.echo(f"permits_real_e2e: {str(result['permits_real_e2e']).lower()}")


@cli.group()
def manifest():
    """Artifact manifest utilities."""
    pass


@manifest.group("miniapp-positive-pilot")
def miniapp_positive_pilot_manifest():
    """TGM MiniApp positive pilot artifact manifest utilities."""
    pass


@miniapp_positive_pilot_manifest.command("validate")
@click.option("--manifest", "manifest_path", required=True, help="Artifact manifest JSON path")
def validate_miniapp_positive_pilot_manifest(manifest_path):
    """Validate a TGM MiniApp positive pilot artifact manifest contract."""
    from tools.validate_miniapp_positive_pilot_artifact_manifest import validate_manifest

    result = validate_manifest(manifest_path)
    status = "PASS" if result.passed else "FAILED"
    click.echo(f"[{status}] MiniApp positive pilot artifact manifest validation")
    click.echo(f"final_status: {result.final_status}")
    click.echo(f"executed_real_runtime: {str(result.executed_real_runtime).lower()}")
    click.echo(f"permits_real_e2e: {str(result.permits_real_e2e).lower()}")
    for warning in result.warnings:
        click.echo(f"[WARN] {warning}")
    for error in result.errors:
        click.echo(f"- {error}")
    if not result.passed:
        sys.exit(1)


@cli.group()
def bundle():
    """Readiness bundle utilities."""
    pass


@bundle.group("miniapp-positive-pilot")
def miniapp_positive_pilot_bundle():
    """TGM MiniApp positive pilot readiness bundle utilities."""
    pass


@miniapp_positive_pilot_bundle.command("validate")
@click.option("--prereq-evidence", required=True, help="Prerequisite evidence JSON")
@click.option("--plan", "plan_path", required=True, help="Positive pilot plan JSON")
@click.option("--dry-run", "dry_run_path", required=True, help="Dry-run manifest JSON")
@click.option("--artifact-manifest", required=True, help="Artifact manifest JSON")
@click.option("--out", required=True, help="Bundle report JSON")
@click.option("--md-out", "md_out", required=True, help="Bundle report Markdown")
def validate_miniapp_positive_pilot_bundle(prereq_evidence, plan_path, dry_run_path, artifact_manifest, out, md_out):
    """Validate consistency across TGM MiniApp positive pilot readiness files."""
    from tools.validate_miniapp_positive_pilot_bundle import validate_bundle

    result = validate_bundle(
        prereq_evidence,
        plan_path,
        dry_run_path,
        artifact_manifest,
        out,
        md_out,
    )
    click.echo(f"bundle_status: {result.report['bundle_status']}")
    click.echo(f"permits_real_e2e: {str(result.report['permits_real_e2e']).lower()}")
    click.echo(f"executed_real_runtime: {str(result.report['executed_real_runtime']).lower()}")
    for blocker in result.report["blockers"]:
        click.echo(f"blocker: {blocker}")
    for failure in result.report["failures"]:
        click.echo(f"- {failure}")
    if result.report["bundle_status"] == "FAILED":
        sys.exit(1)


@cli.group()
def readiness():
    """Readiness decision utilities."""
    pass


@readiness.command("miniapp-positive-pilot")
@click.option("--bundle-report", required=True, help="Bundle report JSON")
@click.option("--out", required=True, help="Readiness report JSON")
@click.option("--md-out", "md_out", required=True, help="Readiness report Markdown")
def evaluate_miniapp_positive_pilot_readiness(bundle_report, out, md_out):
    """Evaluate final local TGM MiniApp positive pilot readiness."""
    from tools.evaluate_miniapp_positive_pilot_readiness import evaluate_readiness

    result = evaluate_readiness(bundle_report, out, md_out)
    click.echo(f"readiness_status: {result.report['readiness_status']}")
    click.echo(f"final_verdict_for_real_e2e: {result.report['final_verdict_for_real_e2e']}")
    click.echo(f"permits_real_e2e: {str(result.report['permits_real_e2e']).lower()}")
    click.echo(f"executed_real_runtime: {str(result.report['executed_real_runtime']).lower()}")
    click.echo(f"required_next_action: {result.report['required_next_action']}")
    for failure in result.report["failures"]:
        click.echo(f"- {failure}")
    if result.report["readiness_status"] == "FAILED":
        sys.exit(1)


@cli.group()
def closeout():
    """Closeout index utilities."""
    pass


@closeout.command("tgm-miniapp-readiness")
@click.option("--out", required=True, help="Closeout JSON path")
@click.option("--md-out", "md_out", required=True, help="Closeout Markdown path")
def generate_tgm_miniapp_readiness_closeout(out, md_out):
    """Generate the TGM MiniApp readiness closeout index."""
    from tools.generate_tgm_miniapp_readiness_closeout import generate_closeout

    report = generate_closeout(out, md_out)
    click.echo(f"closeout_status: {report['status_summary']['current_local_loop_status']}")
    click.echo(f"real_miniapp_e2e_ready: {str(report['status_summary']['real_miniapp_e2e_ready']).lower()}")
    click.echo(
        "runtime_authorization_required_for_real_e2e: "
        f"{str(report['status_summary']['runtime_authorization_required_for_real_e2e']).lower()}"
    )
    click.echo(f"requires_parent_pin_now: {str(report['parent_control_boundary']['requires_parent_pin_now']).lower()}")
    click.echo(f"requires_main_control_now: {str(report['parent_control_boundary']['requires_main_control_now']).lower()}")


if __name__ == "__main__":
    cli()
