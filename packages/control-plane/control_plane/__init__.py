"DevFrame Control Plane — pipeline orchestration engine."
__version__ = "0.1.0"

_PUBLIC_EXPORT_MODULES = {
    "ExecutorAdapter": ".executor_adapter",
    "ExecutorAdapterError": ".executor_adapter",
    "ExecutorAdapterRegistry": ".executor_adapter",
    "ExecutorInvocation": ".executor_adapter",
    "define_executor_adapter": ".executor_adapter",
    "WorkerResult": ".worker",
}
__all__ = tuple(_PUBLIC_EXPORT_MODULES)


def __getattr__(name: str) -> object:
    module_name = _PUBLIC_EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value
