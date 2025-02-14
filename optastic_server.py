from abc import ABC, abstractmethod
import json
from pathlib import Path
from typing import List, Optional
from flask import Flask, request
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
import openai


app = Flask(__name__)


@app.route("/optimize")
def route_optimize():
    project = Path(request.args.get("project"))
    filename = request.args.get("filename")
    lineno = int(request.args.get("line"))
    response = optimize(project, filename, lineno)
    return response


def optimize(project_root: Path, filename: str, lineno: int):
    try:
        client = openai.OpenAI(timeout=30)
    except openai.OpenAIError:
        print("you need an OpenAI key to use this tool.")
        print("You can get a key here: https://platform.openai.com/api-keys.")
        print("set the environment variable OPENAI_API_KEY to your key value.")
        return

    lang = "rust"
    project = Project(project_root, lang)
    with project.lsp().start_server():
        tool_runner = LLMToolRunner(project, [LookupDefinitionTool(), GetLineTool()])

        linestr = project.get_line(filename, lineno - 1)
        messages = [
            {
                "role": "system",
                "content": f"You are a {lang} performance optimization assistant. Please optimize the user's program, making use of the provided tool calls that will let you explore the program.",
            },
            {
                "role": "user",
                "content": f"I've identified line {filename}:{lineno} as a hotspot, reproduced below. Please help me optimize it.\n\n```{lang}\n{linestr}\n```",
            },
        ]
        print(messages)
        response_msg = None
        MAX_ROUNDS = 15
        round_num = 0
        while (
            response_msg is None or response_msg.tool_calls
        ) and round_num <= MAX_ROUNDS:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=tool_runner.all_schemas(),
                tool_choice="auto",
            )
            response_msg = response.choices[0].message
            print(response_msg)
            messages.append(response_msg)
            tool_calls = response_msg.tool_calls

            if tool_calls:
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    func_response = tool_runner.call(func_name, func_args)
                    messages.append(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": func_name,
                            "content": json.dumps(func_response),
                        }
                    )

            round_num += 1
        return response_msg.content


class Project:
    _root: Path
    _lang: str
    _lsp: Optional[SyncLanguageServer]

    def __init__(self, root, lang):
        self._root = root
        self._lang = lang
        self._lsp = None

    def lsp(self) -> SyncLanguageServer:
        if self._lsp is None:
            config = MultilspyConfig.from_dict({"code_language": self._lang})
            logger = MultilspyLogger()
            self._lsp = SyncLanguageServer.create(config, logger, str(self._root))
        return self._lsp

    def get_line(self, filename: str, line: int) -> str:
        assert line >= 0
        with open(self._root.joinpath(filename), "r") as f:
            lines = f.readlines()
            return lines[line]


class LLMTool(ABC):
    schema: dict

    @abstractmethod
    def exec(self, req: dict, project: Project) -> dict:
        pass


class LookupDefinitionTool(LLMTool):
    schema = {
        "type": "function",
        "function": {
            "name": "lookupDefinition",
            "description": "Lookup the definition of a symbol at a particular location",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The filename",
                    },
                    "line": {
                        "type": "integer",
                        "description": "The 1-based line number",
                    },
                    "column": {
                        "type": "integer",
                        "description": "The 1-based column number",
                    },
                },
                "required": ["filename", "line", "column"],
            },
        },
    }

    def exec(self, req: dict, project: Project):
        filename = req["filename"]
        line = int(req["line"])
        column = int(req["column"])
        resp = project.lsp().request_definition(filename, line - 1, column - 1)

        def cvt(r):
            return {
                "relativePath": r["relativePath"],
                "startLine": r["range"]["start"]["line"] + 1,
                "endLine": r["range"]["end"]["line"] + 1,
            }

        return list(map(cvt, resp))


class GetLineTool(LLMTool):
    schema = {
        "type": "function",
        "function": {
            "name": "getLine",
            "description": "Get a line of source code from its filename and line number",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The filename",
                    },
                    "line": {
                        "type": "integer",
                        "description": "The 1-based line number",
                    },
                },
                "required": ["filename", "line"],
            },
        },
    }

    def exec(self, req, project):
        filename = req["filename"]
        line = int(req["line"])
        return project.get_line(filename, line - 1)


class LLMToolRunner:
    def __init__(self, project: Project, tools: List[LLMTool]):
        self._project = project
        self._tools = dict((t.schema["function"]["name"], t) for t in tools)

    def call(self, name: str, args: dict):
        print(f"TOOL CALL {name}: {args}")
        resp = self._tools[name].exec(args, project=self._project)
        print(f"==> {resp}")
        return resp

    def all_schemas(self) -> list[dict]:
        return list(map(lambda tool: tool.schema, self._tools.values()))
