import subprocess
import sys
import uuid
from pathlib import Path

from core.single_instance import acquire

SERVER_DIR = Path(__file__).resolve().parents[1]


def test_second_acquire_is_refused():
    name = f"BlueSendTest-{uuid.uuid4()}"
    assert acquire(name)
    assert not acquire(name)


def test_other_process_is_refused():
    name = f"BlueSendTest-{uuid.uuid4()}"
    assert acquire(name)
    code = (
        "import sys\n"
        "from core.single_instance import acquire\n"
        "sys.exit(0 if acquire(sys.argv[1]) else 1)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, name], cwd=SERVER_DIR, timeout=30
    )
    assert result.returncode == 1
