"""Central settings for ORBIT.

Milestone 1 rule: the ONLY folder ORBIT may scan is the synthetic sample workspace
inside this repository. It's hard-coded on purpose, with no environment variable or
API parameter that could point it at your real Downloads/Documents/Desktop.
"""

from pathlib import Path

# backend/orbit/config.py -> parents[2] is the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The isolated, synthetic folder that the API is allowed to scan.
SAMPLE_WORKSPACE = PROJECT_ROOT / "sample_workspace"

# Read files in 1 MiB chunks so large files never have to fit in memory at once.
HASH_CHUNK_SIZE = 1024 * 1024

# Hard stop so a scan can't run forever on an unexpectedly huge folder.
MAX_FILES_PER_SCAN = 10_000

# The API only answers requests addressed to these hostnames (blocks DNS-rebinding tricks).
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
