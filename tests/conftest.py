import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Nastavení aplikace a uživatelská data (autosave, nedávné) v testech nikdy do domovské složky uživatele.
import tempfile  # noqa: E402

os.environ.setdefault("PIDTOOLS_CONFIG_DIR", tempfile.mkdtemp(prefix="pidtools-cfg-"))
os.environ.setdefault("PIDTOOLS_DATA_DIR", tempfile.mkdtemp(prefix="pidtools-data-"))
