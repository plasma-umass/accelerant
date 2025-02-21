from typing import Dict, List
from pydantic import BaseModel, Field
import openai

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
    def exec(self, req: dict, project: Project) -> dict:
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

    def exec(self, req: dict, project: Project):
        r = self.Model.model_validate(req)

        srclines = project.get_lines(r.filename)
        result = find_symbol(srclines, r.line - 1, r.symbol)
        if result is None:
            return {"error": f"symbol {r.symbol} not found at {r.filename}:{r.line}"}
        line, column = result

        resp = project.lsp().request_definition(r.filename, line, column)

        def cvt(r):
            return {
                "relativePath": r["relativePath"],
                "startLine": r["range"]["start"]["line"] + 1,
                "endLine": r["range"]["end"]["line"] + 1,
            }

        return list(map(cvt, resp))


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

    def exec(self, req: dict, project: Project):
        r = self.Model.model_validate(req)

        srclines = project.get_lines(r.filename)
        result = find_symbol(srclines, r.line - 1, r.symbol)
        if result is None:
            return {"error": "symbol {r.symbol} not found at {r.filename}:{r.line}"}
        line, column = result

        resp = project.lsp().request_hover(r.filename, line, column)
        if resp is None:
            return {
                "error": "no info found for that location (maybe off-by-one error?)"
            }
        return {"contents": resp["contents"]}


class GetCodeTool(LLMTool):
    class Model(BaseModel):
        filename: str = Field(description="The filename")
        line: int = Field(description="The 1-based line number")

    schema = openai.pydantic_function_tool(
        Model,
        name="getCode",
        description="Get several lines of source code near a given line number",
    )

    def exec(self, req: dict, project: Project):
        r = self.Model.model_validate(req)
        filename = r.filename
        line = int(r.line) - 1
        return project.get_lines(filename, line - 3, line + 3)


class LLMToolRunner:
    def __init__(self, project: Project, tools: List[LLMTool]):
        self._project = project
        self._tools: Dict[str, LLMTool] = dict(
            (t.schema["function"]["name"], t) for t in tools
        )

    def call(self, name: str, args: dict):
        print(f"TOOL CALL {name}: {args}")
        tool = self._tools[name]
        resp = tool.exec(args, project=self._project)

        print(f"==> {resp}")
        return resp

    def all_schemas(self) -> list[ChatCompletionToolParam]:
        return list(map(lambda tool: tool.schema, self._tools.values()))
