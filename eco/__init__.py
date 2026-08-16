"""
ECO AGENT — Five-layer loop driven autonomous AI agent system
CLI entry: `eco [command] [options]`
"""

def _detect_version() -> str:
    # Single source of truth: installed package metadata (== pyproject.toml
    # version when installed editable). Fall back to parsing pyproject.toml
    # directly, then to a last-resort constant.
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version("eco-agent")
        except PackageNotFoundError:
            pass
    except ImportError:
        pass
    try:
        import re
        from pathlib import Path
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if pyproject.is_file():
            m = re.search(r'^version\s*=\s*"([^"]+)"',
                          pyproject.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1)
    except OSError:
        pass
    return "1.0.0"  # last resort; keep in sync with pyproject.toml

__version__ = _detect_version()
__author__ = "Taiji Agent Team"
__license__ = "MIT"
