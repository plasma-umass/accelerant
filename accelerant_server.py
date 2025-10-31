import asyncio
from pathlib import Path
from typing import Optional
from flask import Flask, request
from perfparser import LineLoc

from accelerant.agent import AgentConfig, AgentInput, run_agent
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
    # Ensure an asyncio event loop exists in this (Flask request) thread.
    # Needed for OpenAI agents SDK.
    created_loop: Optional[asyncio.AbstractEventLoop] = None
    try:
        try:
            # If a loop is already running in this thread, do nothing.
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop; try getting a set loop or create a new one.
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("Existing event loop is closed")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                created_loop = loop

        project = Project(project_root, "rust")
        print("Starting LSP server")
        with project.lsp().start_server():
            print("Starting agent")
            ag_input: AgentInput = {
                "perf_data_path": perf_data_path,
                "hotspot_lines": [LineLoc(filename, lineno)]
                if filename is not None and lineno is not None
                else None,
            }
            ag_config: AgentConfig = {"model_id": model_id}
            results = run_agent(
                project,
                ag_input,
                ag_config,
            )
            return results["final_message"]
    finally:
        if created_loop is not None and not created_loop.is_closed():
            created_loop.close()


if __name__ == "__main__":
    app.run(debug=True)
