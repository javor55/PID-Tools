import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _isolated_user_dirs(tmp_path_factory):
    """Nastavení aplikace a uživatelská data (autosave, nedávné) se v testech nikdy nezapisují do domovské složky
    a nepřenášejí se mezi moduly (servery spuštěné jako podproces dědí proměnné prostředí)."""
    keys = ("PIDTOOLS_CONFIG_DIR", "PIDTOOLS_DATA_DIR")
    old = {k: os.environ.get(k) for k in keys}
    os.environ["PIDTOOLS_CONFIG_DIR"] = str(tmp_path_factory.mktemp("cfg"))
    os.environ["PIDTOOLS_DATA_DIR"] = str(tmp_path_factory.mktemp("data"))
    yield
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
