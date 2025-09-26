from pathlib import Path
from typing import Literal


class FsSandbox:
    base_dir: Path
    old_versions: dict[Path, str]
    status: Literal["fresh"] | Literal["entered"] | Literal["done"] = "fresh"

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.old_versions = {}

    def __enter__(self) -> "FsSandbox":
        self.status = "entered"
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        assert self.status == "entered"
        for relpath, old_text in self.old_versions.items():
            abspath = self.base_dir / relpath
            with open(abspath, "w") as f:
                f.write(old_text)
        self.status = "done"

    def read_file(self, relpath: Path) -> str:
        assert self.status == "entered"
        abspath = self.base_dir / relpath
        with open(abspath, "r") as f:
            return f.read()

    def write_file(self, relpath: Path, new_text: str) -> None:
        assert self.status == "entered"
        abspath = self.base_dir / relpath
        abspath = self.base_dir / relpath
        if relpath not in self.old_versions:
            with open(abspath, "r") as f:
                self.old_versions[relpath] = f.read()
        with open(abspath, "w") as f:
            f.write(new_text)

    def persist(self, relpath: Path) -> None:
        assert self.status == "entered"
        if relpath in self.old_versions:
            del self.old_versions[relpath]

    def persist_all(self) -> None:
        assert self.status == "entered"
        self.old_versions = {}
