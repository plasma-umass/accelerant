from typing import Dict, List
from pydantic import BaseModel, Field
import openai
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
        column: int = Field(description="The 1-based column number")

    schema = openai.pydantic_function_tool(
        Model,
        name="lookup_definition",
        description="Lookup the definition of a symbol at a particular location",
    )

    def exec(self, req: dict, project: Project):
        r = self.Model.model_validate(req)
        filename = r.filename
        line = int(r.line) - 1
        column = int(r.column) - 1
        resp = project.lsp().request_definition(filename, line, column)

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
        column: int = Field(description="The 1-based column number")

    schema = openai.pydantic_function_tool(
        Model,
        name="get_info",
        description="Get info (like inferred types) about a piece of code",
    )

    def exec(self, req: dict, project: Project):
        r = self.Model.model_validate(req)
        filename = r.filename
        line = r.line - 1
        column = r.column - 1
        resp = project.lsp().request_hover(filename, line, column)
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
