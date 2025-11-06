import os
import shutil
import subprocess
import time
from multilspy.lsp_protocol_handler import lsp_types


from pathlib import Path
from typing import List, Optional

from accelerant.fs_sandbox import FsSandbox, FsVersion
from accelerant.lsp import LSP
from accelerant.perf import PerfData


class Project:
    _root: Path
    # FIXME: this should probably not be here to allow for multiple targets
    _target_binary: Path
    _lang: str
    _fs: FsSandbox
    _lsp: Optional[LSP]
    _perf_per_version: dict[FsVersion, Path]
    _perf_data_map: dict[Path, PerfData]

    def __init__(self, root: Path, target_binary: Path, lang: str) -> None:
        self._root = root
        self._target_binary = target_binary
        self._lang = lang
        self._fs = FsSandbox(root)
        self._lsp = None
        self._perf_per_version = {}
        self._perf_data_map = {}

    def target_binary(self) -> Path:
        return self._target_binary

    def lsp(self) -> LSP:
        if self._lsp is None:
            self._lsp = LSP(self._root, self._lang)
        return self._lsp

    def perf_data(self, version: Optional[FsVersion] = None) -> Optional[PerfData]:
        if version is None:
            version = self.fs_sandbox().version()
        if version not in self._perf_per_version:
            return None
        perf_data_path = self._perf_per_version[version]
        if perf_data_path not in self._perf_data_map:
            self._perf_data_map[perf_data_path] = PerfData(perf_data_path, self._root)
        return self._perf_data_map[perf_data_path]

    def add_perf_data(self, version: FsVersion, perf_data_path: Path) -> None:
        self._perf_per_version[version] = perf_data_path

    def build_for_profiling(self) -> None:
        if self._lang != "rust":
            raise NotImplementedError(
                f"Build for profiling not implemented for language: {self._lang}"
            )

        cargo_path = shutil.which("cargo")
        assert cargo_path is not None, "cargo not found in PATH"

        path_env_var = os.environ.get("PATH")
        assert path_env_var is not None, "PATH environment variable is not set"

        subprocess.run(
            [
                cargo_path,
                "build",
                "--config",
                "profile.release.debug=true",
                "--release",
                "--all-targets",
            ],
            check=True,
            cwd=str(self._root),
            env={"PATH": path_env_var},
        )

    def run_profiler(
        self,
    ) -> None:
        if self._lang != "rust":
            raise NotImplementedError(
                f"Profiler run not implemented for language: {self._lang}"
            )

        perf_data_path = self._root / f"perf{time.time_ns()}.data"

        path_env_var = os.environ.get("PATH")
        assert path_env_var is not None, "PATH environment variable is not set"

        subprocess.run(
            [
                "perf",
                "record",
                "-F99",
                "--call-graph",
                "dwarf",
                "-o",
                str(perf_data_path),
                str(self._target_binary),
            ],
            check=True,
            cwd=str(self._root),
            env={"PATH": path_env_var},
        )
        version = self.fs_sandbox().version()
        self.add_perf_data(version, perf_data_path)

    def fs_sandbox(self) -> FsSandbox:
        return self._fs

    def get_line(self, filename: str, line: int) -> str:
        assert line >= 0
        return self.get_lines(filename, line, line)[0]

    def get_lines(
        self, filename: str, sline: Optional[int] = None, eline: Optional[int] = None
    ) -> List[str]:
        with open(self._root.joinpath(filename), "r") as f:
            lines = list(map(lambda s: s.rstrip(), f.readlines()))
            sline = max(sline or 0, 0)
            maxline = len(lines) - 1
            eline = min(eline or maxline, maxline)
            return lines[sline : eline + 1]

    def get_range(self, filename: str, lsp_range: lsp_types.Range) -> List[str]:
        """Return lines covered by an LSP Range.

        LSP ranges are [start, end) by position. For a line-based slice, we include
        the end line unless end.character == 0, in which case the end line is exclusive.
        """
        start_line = lsp_range["start"]["line"]
        end_line = lsp_range["end"]["line"]
        if lsp_range["end"]["character"] == 0:
            end_line -= 1
        return self.get_lines(filename, start_line, end_line)

    def lang(self) -> str:
        return self._lang
