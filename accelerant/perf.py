from pathlib import Path
from typing import List
from perfparser import get_perf_data, LineLoc

from accelerant.project import Project


class PerfData:
    _perf_data_path: Path
    _project: Project

    def __init__(self, perf_data_path: Path, project: Project):
        self._perf_data_path = perf_data_path
        self._project = project

    def normalize_and_sort(self) -> List[tuple[LineLoc, float]]:
        return get_perf_data(str(self._perf_data_path), str(self._project._root))
