from __future__ import annotations

import os
import tempfile

os.environ["ALTEOR_DATA_DIR"] = tempfile.mkdtemp(prefix="alteor-tests-")
os.environ["ALTEOR_ALLOW_EXTERNAL_CONNECTORS"] = "false"
os.environ["ALTEOR_SEED_DEMO_DATA"] = "true"
