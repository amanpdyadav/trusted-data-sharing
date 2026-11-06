"""Load a .env file into the environment, the way most apps do.

Used only by entry points (the CLI, later the web API); library code keeps reading plain environment variables.
Variables that are already set always win, so a server's or container's real settings are never overridden.
"""

from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def load_env_file(path: str | Path | None = None) -> Path | None:
    """Load `path`, or the nearest .env from the current folder upwards. Returns the file loaded, or None.

    An explicit `path` that does not exist is an error; a missing auto-discovered .env is not.
    """
    if path is not None:
        target = Path(path)
        if not target.is_file():
            raise FileNotFoundError(f"env file not found: {target}")
    else:
        found = find_dotenv(usecwd=True)
        if not found:
            return None
        target = Path(found)
    load_dotenv(target, override=False)
    return target.resolve()
