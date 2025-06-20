from pathlib import Path
from typing import Optional
from flask import Flask, request
from perfparser import LineLoc

from accelerant.chat import optimize_locations
from accelerant.perf import PerfData
from accelerant.project import Project

app = Flask(__name__)


@app.route("/optimize")
def route_optimize() -> str:
    project = request.args.get("project", type=Path)
    if project is None:
        raise Exception("invalid project path")
    filename = request.args.get("filename")
    lineno = request.args.get("line", type=int)
    perf_data_path = request.args.get("perfDataPath", type=Path)
    model_id = request.args.get("modelId", "o3-mini")

    if (filename is None or lineno is None) and perf_data_path is None:
        raise Exception(
            "at least one of (filename and line) or (perfDataPath) must be passed"
        )

    response = optimize(project, filename, lineno, perf_data_path, model_id)
    return response


def optimize(
    project_root: Path,
    filename: Optional[str],
    lineno: Optional[int],
    perf_data_path: Optional[Path],
    model_id: str,
) -> str:
    project = Project(project_root, "rust")
    perf_data = None
    if perf_data_path:
        print("Loading perf data")
        perf_data = PerfData(perf_data_path, project)
    if filename is None or lineno is None:
        assert perf_data is not None
        lines = []
        perf_tabulated = perf_data.tabulate()
        num_hotspots_to_keep = 5
        for hotspot_loc, _ in perf_tabulated[:num_hotspots_to_keep]:
            filename, lineno = hotspot_loc.path, hotspot_loc.line
            lines.append(LineLoc(filename, lineno))
    else:
        lines = [LineLoc(filename, lineno)]
    with project.lsp().start_server():
        print("Starting chat")
        return optimize_locations(project, lines, perf_data, model_id)
