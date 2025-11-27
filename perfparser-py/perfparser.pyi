from typing import List

class LineLoc:
    path: str
    line: int

    def __init__(self, path: str, line: int):
        pass

class AttributedPerf:
    hit_count: dict[LineLoc, int]
    total_hits: int

    def tabulate(self) -> List[tuple[LineLoc, float]]:
        pass

def get_perf_data(data_path_str: str, project_root_str: str) -> AttributedPerf:
    pass
