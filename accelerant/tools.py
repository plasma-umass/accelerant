from dataclasses import dataclass
from typing import Any, Dict, List
from abc import ABC, abstractmethod
from agents import RunContextWrapper, function_tool
from llm_utils import number_group_of_lines
from pydantic import BaseModel, Field
import openai
from openai.types.chat import ChatCompletionToolParam

from accelerant.lsp import TOP_LEVEL_SYMBOL_KINDS, uri_to_relpath
from accelerant.util import find_symbol, truncate_for_llm
from accelerant.project import Project


@dataclass
class AgentContext:
    project: Project


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
