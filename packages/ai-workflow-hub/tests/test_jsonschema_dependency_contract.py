import re
from importlib import import_module
from importlib.metadata import requires


JSONSCHEMA_REQUIREMENT = re.compile(r"^jsonschema(?=\s*(?:$|[<>=!~\[;]))", re.IGNORECASE)
PRODUCTION_MODULES = (
    "ai_workflow_hub.context_layer.builders.paper_context_pack_builder",
    "ai_workflow_hub.context_layer.parsers.bibtex_parser",
    "ai_workflow_hub.context_layer.parsers.obsidian_parser",
    "ai_workflow_hub.context_layer.parsers.zotero_parser",
)


def test_installed_distribution_declares_jsonschema_runtime_contract():
    distribution_requirements = requires("ai-workflow-hub") or []

    assert any(
        JSONSCHEMA_REQUIREMENT.match(requirement)
        and "extra" not in requirement.partition(";")[2].casefold()
        for requirement in distribution_requirements
    ), distribution_requirements

    from jsonschema import Draft7Validator, Draft202012Validator

    assert Draft7Validator.__name__ == "Draft7Validator"
    assert Draft202012Validator.__name__ == "Draft202012Validator"
    for module_name in PRODUCTION_MODULES:
        assert import_module(module_name).__name__ == module_name
