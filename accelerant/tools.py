from dataclasses import dataclass
from itertools import islice
from pathlib import Path
import shutil
import subprocess
from typing import Optional
from agents import RunContextWrapper, ToolOutputImage, function_tool
from llm_utils import number_group_of_lines
from perfparser import LineLoc

from accelerant.chat_interface import CodeSuggestion
from accelerant.flamegraph import make_flamegraph_png, png_to_data_url
from accelerant.lsp import TOP_LEVEL_SYMBOL_KINDS, uri_to_relpath
from accelerant.perf import PerfData
from accelerant.util import find_symbol, truncate_for_llm
from accelerant.project import Project


@dataclass
class AgentContext:
    project: Project


@function_tool
def edit_code(
    ctx: RunContextWrapper[AgentContext],
    sugg: CodeSuggestion,
) -> None:
    """Apply a code suggestion to the project's code. The old code snippet must be unique within the file.

    Args:
        sugg: The code suggestion to apply.
    """
    project = ctx.context.project
    fs = project.fs_sandbox()

    abspath = Path(project._root, sugg.filename)
    old_text = fs.read_file(abspath)
    count = old_text.count(sugg.old_code)
    if count == 0:
        raise ValueError(
            f"Old code snippet not found in {sugg.filename} when applying suggestion."
        )
    elif count > 1:
        raise ValueError(
            f"Old code snippet is not unique in {sugg.filename} when applying suggestion."
        )
    new_text = old_text.replace(sugg.old_code, sugg.new_code)
    fs.write_file(Path(abspath), new_text)


@function_tool
def check_codebase_for_errors(
    ctx: RunContextWrapper[AgentContext],
) -> str:
    """Check the codebase for errors using the appropriate build tool."""
    assert ctx.context.project._lang == "rust", (
        "Only Rust is supported for code checking"
    )

    cargo_path = shutil.which("cargo")
    assert cargo_path is not None, "cargo not found in PATH"
    try:
        subprocess.run(
            [cargo_path, "check", "--all-targets"],
            check=True,
            cwd=str(ctx.context.project._root),
        )
    except subprocess.CalledProcessError as e:
        return f"ERROR: Codebase has errors:\n\n{e}"
    return "OK: Codebase has no errors!"


def _shared_build_and_run_perf(project: Project) -> PerfData:
    version = project.fs_sandbox().version()
    perf_data = project.perf_data(version)
    if perf_data is None:
        project.build_for_profiling()
        project.run_profiler()
        perf_data = project.perf_data(version)
    assert perf_data is not None, "perf data should be available after profiling"
    return perf_data


@function_tool
def run_perf_profiler(
    ctx: RunContextWrapper[AgentContext],
) -> list[dict]:
    """Run a performance profiler on the target binary and return the top hotspots."""
    project = ctx.context.project
    perf_data = _shared_build_and_run_perf(project)
    perf_tabulated = perf_data.tabulate()
    NUM_HOTSPOTS = 5

    def get_parent_region(loc: LineLoc) -> Optional[str]:
        parent_sym = project.lsp().syncexec(
            project.lsp().request_nearest_parent_symbol(
                loc.path, loc.line - 1, TOP_LEVEL_SYMBOL_KINDS
            ),
        )
        if parent_sym is None:
            return None
        return parent_sym["name"]

    hotspots = list(
        islice(
            map(
                lambda x: {
                    "parent_region": get_parent_region(x[0]) or "<unknown>",
                    "loc": x[0],
                    "pct_time": round(x[1] * 100, 1),
                },
                filter(lambda x: x[0].line > 0, perf_tabulated),
            ),
            NUM_HOTSPOTS,
        )
    )
    return hotspots


@function_tool
def generate_flamegraph(
    ctx: RunContextWrapper[AgentContext],
) -> ToolOutputImage:
    """Generate a flamegraph PNG image from the performance data, building the project and running the profiler if necessary."""
    project = ctx.context.project
    perf_data = _shared_build_and_run_perf(project)

    flamegraph_data = make_flamegraph_png(perf_data.data_path())
    flamegraph_data_url = png_to_data_url(flamegraph_data)
    flamegraph_output = ToolOutputImage(image_url=flamegraph_data_url, detail="high")
    return flamegraph_output


@function_tool
def lookup_executable_symbol(ctx: RunContextWrapper[AgentContext], symbol: str) -> dict:
    """
    Lookup a symbol -- in other words, the full path to a function, like `my_crate::my_module::my_function` -- and return its location in the codebase.

    Args:
        symbol: The full symbol name to look up.
    """
    project = ctx.context.project
    binary_path = project.target_binary()
    try:
        result = subprocess.run(
            ["addr2line", "-e", binary_path, symbol + "+0x00"],
            cwd=str(project._root),
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout.strip()
        if output == "??:0":
            return {"error": f"Symbol '{symbol}' not found in binary."}
        filename, line = output.split(":")
        return {"symbol": symbol, "filename": filename, "line": int(line)}
    except Exception as e:
        return {"error": str(e)}


@function_tool
def get_info(
    ctx: RunContextWrapper[AgentContext], filename: str, line: int, symbol: str
) -> list[dict]:
    """Get the definition (including source code), type, and docs of a symbol at a particular location

    Args:
        filename: The filename
        line: The 1-based line number
        symbol: The symbol's text
    """
    project = ctx.context.project

    srclines = project.get_lines(filename)
    result = find_symbol(srclines, line - 1, symbol)
    if result is None:
        raise ValueError(
            f"symbol {symbol} not found at {filename}:{line} (wrong line number?)"
        )
    line, column = result["line_idx"], result["end_chr"]

    resp = project.lsp().syncexec(
        project.lsp().request_definition_full(filename, line, column),
    )
    return list(
        map(
            lambda e: add_info_to_loc(
                add_src_to_loc(convert_lsp_loc(e, project), project),
                project,
                filename,
                line,
                column,
            ),
            resp,
        )
    )


@function_tool
def get_references(
    ctx: RunContextWrapper[AgentContext], filename: str, line: int, symbol: str
) -> list[dict]:
    """Get a list of references, from elsewhere in the code, to a code symbol at a particular location

    Args:
        filename: The filename
        line: The 1-based line number
        symbol: The symbol's text
    """
    project = ctx.context.project

    srclines = project.get_lines(filename)
    result = find_symbol(srclines, line - 1, symbol)
    if result is None:
        raise ValueError(
            f"symbol {symbol} not found at {filename}:{line} (wrong line number?)"
        )
    line, column = result["line_idx"], result["end_chr"]

    resp = project.lsp().syncexec(
        project.lsp().request_references(filename, line, column)
    )
    results = list(
        map(
            lambda r: add_src_to_loc(convert_lsp_loc(dict(r), project), project),
            resp,
        )
    )
    max_results = 10
    if len(results) > max_results:
        return results[:max_results] + [
            {
                "placeholder": f"{len(results) - max_results} more results omitted due to space limitations"
            }
        ]
    else:
        return results


def convert_lsp_loc(r: dict, p: Project) -> dict:
    if "relativePath" in r:
        filename = r["relativePath"]
    else:
        filename = uri_to_relpath(r["targetUri"], str(p._root))
    if "targetRange" in r:
        range = r["targetRange"]
    else:
        range = r["range"]
    sline = range["start"]["line"]
    eline = range["end"]["line"]
    return {
        "filename": filename,
        "startLine": sline + 1,
        "endLine": eline + 1,
    }


def add_src_to_loc(loc: dict, p: Project) -> dict:
    srclines = p.get_lines(loc["filename"], loc["startLine"] - 1, loc["endLine"] - 1)
    if len(srclines) < 100:
        source_code = number_group_of_lines(srclines, loc["startLine"])
    else:
        source_code = number_group_of_lines(
            srclines[:1] + ["<...too long>"], loc["startLine"]
        )
    loc["sourceCode"] = source_code or "<too long>"
    del loc["startLine"]
    del loc["endLine"]
    return loc


def add_info_to_loc(
    loc: dict, p: Project, filename: str, line: int, column: int
) -> dict:
    info = get_hover(p, filename, line, column)
    loc["info"] = info
    return loc


def get_hover(project: Project, filename: str, line: int, column: int):
    resp = project.lsp().syncexec(project.lsp().request_hover(filename, line, column))
    if resp is None:
        return None
    if type(resp["contents"]) is dict and "kind" in resp["contents"]:
        contents = resp["contents"]["value"]
    else:
        raise Exception(f"unsupported textDocument/hover response: {resp}")
    return truncate_for_llm(contents, 1000)


@function_tool
def get_surrounding_code(
    ctx: RunContextWrapper[AgentContext], filename: str, line: int
) -> dict:
    """Get several lines of source code near a given line number

    Args:
        filename: The filename
        line: The 1-based line number
    """
    project = ctx.context.project

    parent_sym = project.lsp().syncexec(
        project.lsp().request_nearest_parent_symbol(
            filename, line - 1, TOP_LEVEL_SYMBOL_KINDS
        ),
    )
    if parent_sym is None:
        raise ValueError(f"no surrounding top-level symbol found at {filename}:{line}")
    sline = parent_sym["range"]["start"]["line"] + 1
    lines = project.get_range(filename, parent_sym["range"])
    return {
        "filename": filename,
        "region_name": parent_sym["name"],
        "code": number_group_of_lines(lines, max(sline, 1)),
    }
