from typing import List

class LineLoc:
    path: str
    line: int

def get_perf_data(
    data_path_str: str, project_root_str: str
) -> List[tuple[LineLoc, float]]:
    pass
