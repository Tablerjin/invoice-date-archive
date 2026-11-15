"""Replace output entries atomically without following target symlinks."""
import os
import tempfile
from pathlib import Path


def replace_output(output, writer):
    output = Path(output)
    fd, temporary = tempfile.mkstemp(prefix='.invoice-output-', suffix=output.suffix, dir=str(output.parent))
    os.close(fd)
    try:
        writer(Path(temporary))
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
