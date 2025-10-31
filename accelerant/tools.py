from dataclasses import dataclass
from itertools import islice
from pathlib import Path
import subprocess
from typing import Any, Optional
from agents import RunContextWrapper, function_tool
from llm_utils import number_group_of_lines
from perfparser import LineLoc

from accelerant.chat_interface import CodeSuggestion
from accelerant.fs_sandbox import FsSandbox
from accelerant.lsp import TOP_LEVEL_SYMBOL_KINDS, uri_to_relpath
from accelerant.patch import apply_simultaneous_suggestions
from accelerant.util import find_symbol, truncate_for_llm
from accelerant.project import Project


@dataclass
class AgentContext:
    project: Project
    active_fs: FsSandbox
    initial_perf_data_path: Optional[Path]


@function_tool
def edit_code(
    ctx: RunContextWrapper[AgentContext],
    suggs: list[CodeSuggestion],
) -> None:
    """Apply edits to the codebase based on suggestions.

    Args:
        suggs: A list of code suggestions that should be applied.
    """
    apply_simultaneous_suggestions(ctx.context.project, ctx.context.active_fs, suggs)


@function_tool
def check_codebase_for_errors(
    ctx: RunContextWrapper[AgentContext],
) -> str:
    """Check the codebase for errors using the appropriate build tool."""
    assert ctx.context.project._lang == "rust", (
        "Only Rust is supported for code checking"
    )
    try:
        subprocess.run(
            ["cargo", "check", "--all"], check=True, cwd=str(ctx.context.project._root)
        )
    except subprocess.CalledProcessError as e:
        return f"ERROR: Codebase has errors:\n\n{e}"
    return "OK: Codebase has no errors!"


@function_tool
def get_profiler_data(
    ctx: RunContextWrapper[AgentContext],
) -> list[dict[str, Any]]:
    """Get a summary of the objective performance data gathered by a profiler."""
    try:
        perf_data_path = ctx.context.initial_perf_data_path
        if perf_data_path is None:
            raise ValueError("No initial performance data path provided")
        project = ctx.context.project
        perf_data = project.perf_data(perf_data_path)
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

        hotspots = islice(
            map(
                lambda x: {
                    "parent_region": get_parent_region(x[0]) or "<unknown>",
                    "loc": x[0],
                    "pct_time": x[1] * 100,
                },
                filter(lambda x: x[0].line > 0, perf_tabulated),
            ),
            NUM_HOTSPOTS,
        )
        return list(hotspots)
    except Exception as e:
        print("ERROR", e)
        raise e


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
    # FIXME: avoid crashing
    assert parent_sym is not None
    sline = parent_sym["range"]["start"]["line"] + 1
    lines = project.get_range(filename, parent_sym["range"])
    return {
        "filename": filename,
        "regionName": parent_sym["name"],
        "code": number_group_of_lines(lines, max(sline, 1)),
    }
