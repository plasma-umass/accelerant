from abc import ABC, abstractmethod
import json
from pathlib import Path
from flask import Flask, request
import openai

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
        messages = [
            {
                "role": "system",
                "content": f"You are a {lang} performance optimization assistant. Please optimize the user's program, making use of the provided tool calls that will let you explore the program. Never make assumptions about the program; use tool calls if you are not sure.",
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
            tool_schemas = tool_runner.all_schemas()
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=tool_schemas,
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
