from typing import Dict, List
from multilspy import SyncLanguageServer
from pydantic import BaseModel, Field
import openai
from .project import Project
from openai.types.chat import ChatCompletionToolParam


from abc import ABC

openai.pydantic_function_tool


class LLMTool(ABC):
    schema: ChatCompletionToolParam

    @property
    def params_type(self) -> BaseModel:
        pass

    def exec(self, req: BaseModel, lsp: SyncLanguageServer) -> dict:
        pass


class LookupDefinitionTool(LLMTool):
    class LookupDefinition(BaseModel):
        filename: str = Field(description="The filename", required=True)
        line: int = Field(description="The 1-based line number", required=True)
        column: int = Field(description="The 1-based column number", required=True)

    schema = openai.pydantic_function_tool(
        LookupDefinition,
        name="lookup_definition",
        description="Lookup the definition of a symbol at a particular location",
    )
    params_type = LookupDefinition

    def exec(self, req: LookupDefinition, project: Project):
        filename = req.filename
        line = int(req.line) - 1
        column = int(req.column) - 1
        resp = project.lsp().request_definition(filename, line, column)

        def cvt(r):
            return {
                "relativePath": r["relativePath"],
                "startLine": r["range"]["start"]["line"] + 1,
                "endLine": r["range"]["end"]["line"] + 1,
            }

        return list(map(cvt, resp))

class GetInfoTool(LLMTool):
    class GetInfo(BaseModel):
        filename: str = Field(description="The filename", required=True)
        line: int = Field(description="The 1-based line number", required=True)
        column: int = Field(description="The 1-based column number", required=True)

    schema = openai.pydantic_function_tool(
        GetInfo,
        name="get_info",
        description="Get info (like inferred types) about a piece of code",
    )
    params_type = GetInfo
    def exec(self, req: GetInfo, project: Project):
        filename = req.filename
        line = req.line - 1
        column = req.column - 1
        resp = project.lsp().request_hover(filename, line, column)
        if resp is None:
            return {
                "error": "no info found for that location (maybe off-by-one error?)"
            }
        return {"contents": resp["contents"]}
# schema = {
#     "type": "function",
#     "function": {
#         "name": "getLine",
#         "description": "Get several lines of source code near a given line number",
#         "parameters": {
#             "type": "object",
#             "properties": {
#                 "filename": {
#                     "type": "string",
#                     "description": "The filename",
#                 },
#                 "line": {
#                     "type": "integer",
#                     "description": "The 1-based line number",
#                 },
#             },
#             "required": ["filename", "line"],
#         },
#     },
# }

class GetCodeTool(LLMTool):
    class GetCode(BaseModel):
        filename: str = Field(description="The filename", required=True)
        line: int = Field(description="The 1-based line number", required=True)

    schema = openai.pydantic_function_tool(
        GetCode,
        name="getLine",
        description="Get several lines of source code near a given line number",
    )
    params_type = GetCode

    def exec(self, req: GetCode, project: Project):
        filename = req.filename
        line = int(req.line) - 1
        return project.get_lines(filename, line - 3, line + 3)


class LLMToolRunner:
    def __init__(self, project: Project, tools: List[LLMTool]):
        self._project = project
        self._tools: Dict[str, LLMTool] = dict((t.schema["function"]["name"], t) for t in tools)

    def call(self, name: str, args: dict):
        print(f"TOOL CALL {name}: {args}")
        tool = self._tools[name]
        resp = tool.exec(tool.params_type.model_validate(args), project=self._project)

        print(f"==> {resp}")
        return resp

    def all_schemas(self) -> list[dict]:
        return list(map(lambda tool: tool.schema, self._tools.values()))