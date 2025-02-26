from pathlib import Path
from flask import Flask, request

from optastic.chat import run_chat
from optastic.project import Project

app = Flask(__name__)


@app.route("/optimize")
def route_optimize():
    project = Path(request.args.get("project"))
    filename = request.args.get("filename")
    lineno = int(request.args.get("line"))
    response = optimize(project, filename, lineno)
    return response


def optimize(project_root: Path, filename: str, lineno: int):
    project = Project(project_root, "rust")
    with project.lsp().start_server():
        return run_chat(project, filename, lineno)
