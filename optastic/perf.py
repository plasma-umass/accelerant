from pathlib import Path
import subprocess
from typing import Callable, Iterator, List, Optional

from optastic.project import Project


class PerfData:
    counts: dict[tuple[Path, int], int]

    def __init__(self, perf_data_path: Path, project: Project):
        def is_srcline_good(path: Path):
            return project._root in path.parents

        perf_lines = iter(run_perf_script(perf_data_path))

        counts = {}
        while True:
            try:
                result = extract_srcline_from_perf_entry(perf_lines, is_srcline_good)
                if not result:
                    continue
                sym, lineno = result
            except StopIteration:
                break
            if (sym, lineno) not in counts:
                counts[(sym, lineno)] = 0
            counts[(sym, lineno)] += 1
        self.counts = counts

    def normalize_and_sort(self) -> List[tuple[tuple[Path, int], float]]:
        tot_samples = sum(self.counts.values())
        counts_srt = list(
            map(
                lambda kv: (kv[0], kv[1] / tot_samples),
                sorted(self.counts.items(), key=lambda kv: kv[1], reverse=True),
            )
        )
        return counts_srt


def extract_srcline_from_perf_entry(
    lines: Iterator[str], is_srcline_good: Callable[[Path], bool]
) -> Optional[tuple[Path, int]]:
    """
    Parses a `perf script` entry from the provided iterator,
    and returns the first "good" line location from the stack trace,
    based on the provided callback.

    Meant to be run on output from `perf script -F+srcline --full-source-path`.
    """

    _ = next(lines)  # skip header
    while True:
        line = next(lines).strip()  # ip/sym
        if not line:
            break
        line = next(lines).strip()  # srcline
        if not line:
            break
        loc, *info = line.split(" ", 1)
        if ":" not in loc:
            continue
        split_results = loc.rsplit(":", 1)
        path, lineno = Path(split_results[0]), int(split_results[1])
        if is_srcline_good(path):
            return path, lineno

    return None


def run_perf_script(perf_data_path: Path) -> List[str]:
    PERF_CMD = [
        "perf",
        "script",
        "-F+srcline",
        "--full-source-path",
        "-i",
        str(perf_data_path),
    ]
    out_bytes = subprocess.check_output(PERF_CMD)
    return out_bytes.decode().splitlines()
