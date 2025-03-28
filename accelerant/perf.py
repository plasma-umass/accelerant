from pathlib import Path
from typing import List, Optional
from perfparser import get_perf_data, LineLoc

from accelerant.project import Project
from perfparser import AttributedPerf


class PerfData:
    _data: AttributedPerf

    def __init__(self, perf_data_path: Path, project: Project):
        self._data = get_perf_data(str(perf_data_path), str(project._root))

    def lookup_pct_time(self, loc: LineLoc) -> Optional[float]:
        if loc not in self._data.hit_count:
            return None
        return self._data.hit_count[loc] / self._data.total_hits

    def tabulate(self) -> List[tuple[LineLoc, float]]:
        return self._data.tabulate()
