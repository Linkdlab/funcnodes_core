import pathlib
import os
import pytest

try:
    import yappi
except ImportError:
    yappi = None


class _yappicontext:
    def __init__(self, file):
        base_dir = pathlib.Path(
            os.environ.get("TEST_OUTPUT_DIR", "testouts")
        ).absolute()
        if not base_dir.exists():
            base_dir.mkdir(parents=True, exist_ok=True)
        self.file = str(base_dir / file)

    def __enter__(self):
        if yappi is not None:
            yappi.set_clock_type("WALL")
            yappi.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if yappi is not None:
            yappi.stop()
            yappi.get_func_stats().save(self.file, "pstat")
            yappi.clear_stats()


@pytest.fixture
def yappicontext_class():
    return _yappicontext


@pytest.fixture
def yappicontext(yappicontext_class, request):
    return yappicontext_class(request.node.name + ".pstat")
