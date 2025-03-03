from typing import Any, Dict, List
from abc import ABC, abstractmethod
from llm_utils import number_group_of_lines
from pydantic import BaseModel, Field
import openai
from openai.types.chat import ChatCompletionToolParam

from optastic.lsp import request_definition_full, syncexec, extract_relative_path
from optastic.util import find_symbol, truncate_for_llm
from optastic.project import Project


class LLMTool(ABC):
    @property
    @abstractmethod
    def schema(self) -> ChatCompletionToolParam:
        pass

    @abstractmethod
    def exec(self, req: dict, project: Project) -> Any:
        pass


class GetDefinitionTool(LLMTool):
    class Model(BaseModel):
        filename: str = Field(description="The filename")
        line: int = Field(description="The 1-based line number")
        symbol: str = Field(description="The symbol's text")

    schema = openai.pydantic_function_tool(
        Model,
        name="get_definition",
        description="Get the definition (including source code) of a symbol at a particular location",
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

        resp = syncexec(
            project.lsp(),
            request_definition_full(
                project.lsp().language_server, r.filename, line, column
            ),
        )
        return list(
            map(lambda r: add_src_to_loc(convert_lsp_loc(r, project), project), resp)
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

        resp = project.lsp().request_references(r.filename, line, column)
        return list(
            map(
                lambda r: add_src_to_loc(convert_lsp_loc(dict(r), project), project),
                resp,
            )
        )


def convert_lsp_loc(r: dict, p: Project) -> dict:
    if "relativePath" in r:
        filename = r["relativePath"]
    else:
        filename = extract_relative_path(r["targetUri"], p)
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
    return loc


class GetTypeAndDocsTool(LLMTool):
    class Model(BaseModel):
        filename: str = Field(description="The filename")
        line: int = Field(description="The 1-based line number")
        symbol: str = Field(description="The symbol's text")

    schema = openai.pydantic_function_tool(
        Model,
        name="get_type_and_docs",
        description="Get info (like inferred types and documentation) about a code symbol at a particular location",
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

        resp = project.lsp().request_hover(r.filename, line, column)
        if resp is None:
            return {"error": "no info found for that location (wrong line number?)"}
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
        sline, eline = line - 5, line + 5
        lines = project.get_lines(filename, sline, eline)
        return number_group_of_lines(lines, max(sline + 1, 1))


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
