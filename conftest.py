import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.resolve()
_EXPECTED_VENV = (_REPO_ROOT / ".venv").resolve()
_ACTIVE_PREFIX = Path(sys.prefix).resolve()

if _ACTIVE_PREFIX != _EXPECTED_VENV:
    raise SystemExit(
        f"ERROR: Tests must run inside this project's virtual environment.\n"
        f"Expected: {_EXPECTED_VENV}\n"
        f"Active:   {_ACTIVE_PREFIX}\n\n"
        f"Activate it first:\n"
        f"  source .venv/bin/activate\n"
        f"Or invoke pytest through the venv directly:\n"
        f"  .venv/bin/pytest"
    )
