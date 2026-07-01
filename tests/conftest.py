"""Test-only setup. Runs before any test module imports `app.api`, so the
module-level default app uses a throwaway OUTPUT_DIR instead of polluting the
host (e.g. creating D:\\outputs on Windows). Production uses /outputs."""
import os
import tempfile

os.environ.setdefault("OUTPUT_DIR", tempfile.mkdtemp(prefix="trellis-test-out-"))
