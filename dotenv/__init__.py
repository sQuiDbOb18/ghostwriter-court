import os
from pathlib import Path


def load_dotenv(path: str | os.PathLike[str] = ".env") -> bool:
    env_path = Path(path)
    if not env_path.exists():
        return False

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)

    return True
