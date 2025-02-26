from pathlib import Path
from flask import Flask, request

from optastic.chat import run_chat
from optastic.project import Project

app = Flask(__name__)


@app.route("/optimize")
def route_optimize():
    project = request.args.get("project", type=Path)
    if project is None:
        raise Exception("invalid project path")
    filename = request.args.get("filename")
    lineno = request.args.get("line", type=int)
    if lineno is None:
        raise Exception("invalid line number")
    model_id = request.args.get("modelId", "o3-mini")

    response = optimize(project, filename, lineno, model_id)
    return response


def optimize(project_root: Path, filename: str, lineno: int, model_id: str) -> str:
    project = Project(project_root, "rust")
    with project.lsp().start_server():
        return run_chat(project, filename, lineno, model_id)
