"""Resolve Supabase credentials from env vars, or a .env in cwd / repo root."""
import os

_KEYS = ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "API_KEY")


def _load_env_file():
    here = os.getcwd()
    candidates = [os.path.join(here, ".env"),
                  os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")]
    for path in candidates:
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return


def get():
    """Return (supabase_url, secret_key). Raises a clear error if missing."""
    if not os.environ.get("SUPABASE_URL"):
        _load_env_file()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        raise SystemExit(
            "Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_SECRET_KEY "
            "as env vars, or put them in a .env file in this directory."
        )
    return url.rstrip("/"), key
