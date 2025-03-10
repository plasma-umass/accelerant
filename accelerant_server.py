import os
from pathlib import Path
from typing import Optional
from flask import Flask, request

from accelerant.chat import run_chat
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
        perf_data = PerfData(perf_data_path, project)
    if filename is None or lineno is None:
        assert perf_data is not None
        abspath, lineno = perf_data.normalize_and_sort()[0][0]
        filename = os.path.relpath(abspath, project._root)
    with project.lsp().start_server():
        return run_chat(project, filename, lineno, model_id)
