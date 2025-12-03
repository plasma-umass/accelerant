import asyncio
from pathlib import Path
from typing import Optional
from flask import Flask, request
from perfparser import LineLoc

from accelerant.agent import AgentConfig, AgentInput, run_agent
from accelerant.project import Project
from accelerant.startup import setup_prereqs

app = Flask(__name__)


@app.route("/optimize")
def route_optimize() -> str:
    project = request.args.get("project", type=Path)
    if project is None:
        raise Exception("invalid project path")
    target_binary = request.args.get("targetBinary", type=Path)
    if target_binary is None:
        raise Exception("invalid target binary path")
    # FIXME: this is just a temporary sanity check. ideally this would be more robust.
    assert "release" in str(target_binary), "target binary must be a release build"
    filename = request.args.get("filename")
    lineno = request.args.get("line", type=int)
    perf_data_path = request.args.get("perfDataPath", type=Path)
    model_id = request.args.get("modelId", "gpt-4.1")

    response = optimize(
        project, target_binary, filename, lineno, perf_data_path, model_id
    )
    return response


def optimize(
    project_root: Path,
    target_binary: Path,
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

        project = Project(project_root, target_binary, "rust")
        if perf_data_path is not None:
            project.add_perf_data(project.fs_sandbox().version(), perf_data_path)
        print("Starting LSP server")
        with project.lsp().start_server():
            with project.fs_sandbox():
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
    setup_prereqs()
    app.run(debug=True)
