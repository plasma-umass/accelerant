from typing import Any, Dict, List
from llm_utils import number_group_of_lines
from pydantic import BaseModel, Field
import openai

from optastic.lsp import request_implementation, syncexec, extract_relative_path
from optastic.util import find_symbol
from .project import Project
from openai.types.chat import ChatCompletionToolParam


from abc import ABC, abstractmethod

openai.pydantic_function_tool


class LLMTool(ABC):
    @property
    @abstractmethod
    def schema(self) -> ChatCompletionToolParam:
        pass

    @abstractmethod
    def exec(self, req: dict, project: Project) -> Any:
        pass


class LookupDefinitionTool(LLMTool):
    class Model(BaseModel):
        filename: str = Field(description="The filename")
        line: int = Field(description="The 1-based line number")
        symbol: str = Field(description="The symbol's text")

    schema = openai.pydantic_function_tool(
        Model,
        name="lookup_definition",
        description="Lookup the definition of a symbol at a particular location",
    )

    def exec(self, req: dict, project: Project) -> Any:
        r = self.Model.model_validate(req)

        srclines = project.get_lines(r.filename)
        result = find_symbol(srclines, r.line - 1, r.symbol)
        if result is None:
            return {
                "error": f"symbol {r.symbol} not found at {r.filename}:{r.line} (wrong line number?)"
            }
        line, column = result

        resp = syncexec(
            project.lsp(),
            request_implementation(
                project.lsp().language_server, r.filename, line, column
            ),
        )

        def cvtLoc(r: dict, p: Project):
            if "relativePath" in r:
                filename = r["relativePath"]
            else:
                filename = extract_relative_path(r["targetUri"], p)
            range = r["targetRange"]
            sline = range["start"]["line"]
            eline = range["end"]["line"]
            return {
                "filename": filename,
                "startLine": sline + 1,
                "endLine": eline + 1,
            }

        def addSrc(loc: dict, p: Project):
            srclines = p.get_lines(
                loc["filename"], loc["startLine"] - 1, loc["endLine"] - 1
            )
            if len(srclines) < 100:
                source_code = number_group_of_lines(srclines, loc["startLine"])
            else:
                source_code = number_group_of_lines(
                    srclines[:1] + ["<...too long>"], loc["startLine"]
                )
            loc["sourceCode"] = source_code or "<too long>"
            return loc

        return list(map(lambda r: addSrc(cvtLoc(r, project), project), resp))


class GetInfoTool(LLMTool):
    class Model(BaseModel):
        filename: str = Field(description="The filename")
        line: int = Field(description="The 1-based line number")
        symbol: str = Field(description="The symbol's text")

    schema = openai.pydantic_function_tool(
        Model,
        name="get_info",
        description="Get info (like inferred types) about a code symbol at a particular location",
    )

    def exec(self, req: dict, project: Project) -> Any:
        r = self.Model.model_validate(req)

        srclines = project.get_lines(r.filename)
        result = find_symbol(srclines, r.line - 1, r.symbol)
        if result is None:
            return {
                "error": "symbol {r.symbol} not found at {r.filename}:{r.line} (wrong line number?)"
            }
        line, column = result

        resp = project.lsp().request_hover(r.filename, line, column)
        if resp is None:
            return {"error": "no info found for that location (wrong line number?)"}
        return {"contents": resp["contents"]}


class GetCodeTool(LLMTool):
    class Model(BaseModel):
        filename: str = Field(description="The filename")
        line: int = Field(description="The 1-based line number")

    schema = openai.pydantic_function_tool(
        Model,
        name="get_code",
        description="Get several lines of source code near a given line number",
    )

    def exec(self, req: dict, project: Project) -> Any:
        r = self.Model.model_validate(req)
        filename = r.filename
        line = int(r.line) - 1
        sline, eline = line - 3, line + 3
        lines = project.get_lines(filename, sline, eline)
        return number_group_of_lines(lines, sline + 1)


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
