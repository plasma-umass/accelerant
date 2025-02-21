import json
from pathlib import Path
from typing import Any, List
from flask import Flask, request
import openai
from rich import print as rprint
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion import ChatCompletion

from optastic.project import Project
from optastic.tools import LookupDefinitionTool, GetCodeTool, GetInfoTool
from optastic.tools import LLMToolRunner

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
        tool_runner = LLMToolRunner(
            project, [LookupDefinitionTool(), GetCodeTool(), GetInfoTool()]
        )

        linestr = project.get_line(filename, lineno - 1)
        messages: List[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": f"You are a {lang} performance optimization assistant. Please optimize the user's program, making use of the provided tool calls that will let you explore the program. Never make assumptions about the program; use tool calls if you are not sure.",
            },
            {
                "role": "user",
                "content": f"I've identified line {filename}:{lineno} as a hotspot, reproduced below. Please help me optimize it.\n\n```{lang}\n{linestr}\n```",
            },
        ]
        for msg in messages:
            _print_message(msg)

        response_msg = None
        MAX_ROUNDS = 15
        round_num = 0
        while (
            response_msg is None or response_msg.tool_calls
        ) and round_num <= MAX_ROUNDS:
            tool_schemas = tool_runner.all_schemas()
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=tool_schemas,
                tool_choice="auto",
            )
            _print_completion(response)
            response_msg = response.choices[0].message
            messages.append(response_msg)  # type: ignore
            tool_calls = response_msg.tool_calls

            if tool_calls:
                rprint("Tool responses:")
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    func_response = tool_runner.call(func_name, func_args)
                    rprint(f"  {func_name} =>", func_response)
                    messages.append(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "content": json.dumps(func_response),
                        }
                    )

            round_num += 1

        assert response_msg is not None
        return response_msg.content


def _print_message(msg: Any):
    if type(msg) is dict:
        role = msg["role"]
        content = msg["content"]
    else:
        role = msg.role
        content = msg.content
    rprint(f"[purple]{role}:[/purple] {content}")


def _print_completion(completion: ChatCompletion):
    response = completion.choices[0].message
    rprint(f"[orange]Choice 1/{len(completion.choices)}[/orange]:")
    _print_message(response)
    if response.tool_calls:
        rprint("[blue]Tool calls:[/blue]")
        for call in response.tool_calls:
            funcname = call.function.name
            funcargs = call.function.arguments
            rprint(f"  {funcname} =>", funcargs)
