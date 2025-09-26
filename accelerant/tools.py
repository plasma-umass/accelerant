from typing import Any, Dict, List
from abc import ABC, abstractmethod
from llm_utils import number_group_of_lines
from pydantic import BaseModel, Field
import openai
from openai.types.chat import ChatCompletionToolParam

from accelerant.lsp import TOP_LEVEL_SYMBOL_KINDS, uri_to_relpath
from accelerant.util import find_symbol, truncate_for_llm
from accelerant.project import Project


class LLMTool(ABC):
    @property
    @abstractmethod
    def schema(self) -> ChatCompletionToolParam:
        pass

    @abstractmethod
    def exec(self, req: dict, project: Project) -> Any:
        pass


class GetInfoTool(LLMTool):
    class Model(BaseModel):
        filename: str = Field(description="The filename")
        line: int = Field(description="The 1-based line number")
        symbol: str = Field(description="The symbol's text")

    schema = openai.pydantic_function_tool(
        Model,
        name="get_info",
        description="Get the definition (including source code), type, and docs of a symbol at a particular location",
    )

    def exec(self, req: dict, project: Project) -> Any:
        r = self.Model.model_validate(req)

        srclines = project.get_lines(r.filename)
        result = find_symbol(srclines, r.line - 1, r.symbol)
        if result is None:
            return {
                "error": f"symbol {r.symbol} not found at {r.filename}:{r.line} (wrong line number?)"
            }
        line, column = result["line_idx"], result["end_chr"]

        resp = project.lsp().syncexec(
            project.lsp().request_definition_full(r.filename, line, column),
        )
        return list(
            map(
                lambda e: add_info_to_loc(
                    add_src_to_loc(convert_lsp_loc(e, project), project),
                    project,
                    r.filename,
                    line,
                    column,
                ),
                resp,
            )
        )


class GetReferencesTool(LLMTool):
    class Model(BaseModel):
        filename: str = Field(description="The filename")
        line: int = Field(description="The 1-based line number")
        symbol: str = Field(description="The symbol's text")

    schema = openai.pydantic_function_tool(
        Model,
        name="get_references",
        description="Get a list of references, from elsewhere in the code, to a code symbol at a particular location",
    )

    def exec(self, req: dict, project: Project) -> Any:
        r = self.Model.model_validate(req)

        srclines = project.get_lines(r.filename)
        result = find_symbol(srclines, r.line - 1, r.symbol)
        if result is None:
            return {
                "error": "symbol {r.symbol} not found at {r.filename}:{r.line} (wrong line number?)"
            }
        line, column = result["line_idx"], result["end_chr"]

        resp = project.lsp().syncexec(
            project.lsp().request_references(r.filename, line, column)
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


class GetSurroundingCodeTool(LLMTool):
    class Model(BaseModel):
        filename: str = Field(description="The filename")
        line: int = Field(description="The 1-based line number")

    schema = openai.pydantic_function_tool(
        Model,
        name="get_surrounding_code",
        description="Get several lines of source code near a given line number",
    )

    def exec(self, req: dict, project: Project) -> Any:
        r = self.Model.model_validate(req)
        filename = r.filename
        line = int(r.line) - 1
        parent_sym = project.lsp().syncexec(
            project.lsp().request_nearest_parent_symbol(
                filename, line, TOP_LEVEL_SYMBOL_KINDS
            ),
        )
        # FIXME: avoid crashing
        assert parent_sym is not None
        sline = parent_sym["range"]["start"]["line"] + 1
        lines = project.get_range(filename, parent_sym["range"])
        return {
            "filename": r.filename,
            "regionName": parent_sym["name"],
            "code": number_group_of_lines(lines, max(sline, 1)),
        }


class LLMToolRunner:
    def __init__(self, project: Project, tools: List[LLMTool]):
        self._project = project
        self._tools: Dict[str, LLMTool] = dict(
            (t.schema["function"]["name"], t) for t in tools
        )

    def call(self, name: str, args: dict):
        tool = self._tools[name]
        resp = tool.exec(args, project=self._project)
        return resp

    def all_schemas(self) -> list[ChatCompletionToolParam]:
        return list(map(lambda tool: tool.schema, self._tools.values()))
