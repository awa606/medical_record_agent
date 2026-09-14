from pathlib import Path


def pytest_sessionstart(session) -> None:
    """Create the parent required by pytest's project-local --basetemp."""
    Path(".artifacts").mkdir(parents=True, exist_ok=True)
