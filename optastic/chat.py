import json
from rich.markup import escape as rescape
from typing import Any, List
from llm_utils import number_group_of_lines
import openai
from openai.types.chat import (
    ChatCompletionDeveloperMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ParsedChatCompletion,
)
from pydantic import BaseModel
from rich import print as rprint

from optastic.project import Project
from optastic.tools import (
    GetReferencesTool,
    GetSurroundingCodeTool,
    GetTypeAndDocsTool,
    LLMToolRunner,
    GetDefinitionTool,
)


class OptimizationSuggestion(BaseModel):
    filename: str
    startLine: int
    endLine: int
    newCode: str


class OptimizationSuite(BaseModel):
    highLevelSummary: str
    suggestions: List[OptimizationSuggestion]


def run_chat(project: Project, filename: str, lineno: int, model_id: str):
    lang = project.lang()

    try:
        client = openai.OpenAI(timeout=90)
    except openai.OpenAIError:
        print("you need an OpenAI key to use this tool.")
        print("You can get a key here: https://platform.openai.com/api-keys.")
        print("set the environment variable OPENAI_API_KEY to your key value.")
        return

    tool_runner = LLMToolRunner(
        project,
        [
            GetDefinitionTool(),
            GetReferencesTool(),
            GetTypeAndDocsTool(),
            GetSurroundingCodeTool(),
        ],
    )

    prettyline = number_group_of_lines(
        project.get_lines(filename, lineno - 1 - 5, lineno - 1 + 5),
        max(lineno - 5, 1),
    )
    messages: List[ChatCompletionMessageParam] = [
        _make_system_message(
            model_id,
            f"You are a {lang} performance optimization assistant. You NEVER make assumptions or express hypotheticals about what the user's program does. Instead, you make ample use of the tool calls available to you to thoroughly explore the user's program. You always give CONCRETE code suggestions.",
        ),
        {
            "role": "user",
            "content": f"I've identified line {filename}:{lineno} as a hotspot, reproduced below. Please help me optimize it by exploring the program and giving me CONCRETE suggestions.\n\n```{lang}\n{prettyline}\n```",
        },
    ]
    for msg in messages:
        _print_message(msg)

    response_msg = None
    MAX_ROUNDS = 30
    round_num = 0
    while (response_msg is None or response_msg.tool_calls) and round_num <= MAX_ROUNDS:
        tool_schemas = tool_runner.all_schemas()
        response = client.beta.chat.completions.parse(
            model=model_id,
            messages=messages,
            tools=tool_schemas,
            tool_choice="auto",
            response_format=OptimizationSuite,
        )
        _print_completion(response)
        response_msg = response.choices[0].message
        messages.append(response_msg)  # type: ignore
        tool_calls = response_msg.tool_calls

        if tool_calls:
            rprint("[blue]Tool responses:[/blue]")
            for tool_call in tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                func_response = tool_runner.call(func_name, func_args)
                rprint(f"  {func_name} =>", smart_escape(func_response))
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


def _make_system_message(
    model_id: str, content: str
) -> ChatCompletionSystemMessageParam | ChatCompletionDeveloperMessageParam:
    if model_id.startswith("o"):
        return {"role": "developer", "content": content}
    elif model_id.startswith("gpt"):
        return {"role": "system", "content": content}
    else:
        raise Exception(f"unknown model id {model_id}")


def _print_message(msg: Any):
    if type(msg) is dict:
        role = msg["role"]
        content = msg["content"]
    else:
        role = msg.role
        content = msg.content
    rprint(f"[purple]{rescape(role)}:[/purple] {smart_escape(content)}")


def _print_parsed_completion(parsed: OptimizationSuite):
    rprint("[underline]High-level Summary[/underline]")
    rprint(rescape(parsed.highLevelSummary))
    rprint()

    for sugg in parsed.suggestions:
        rprint(
            f"[underline]In {rescape(sugg.filename)}, replace lines {sugg.startLine} to {sugg.endLine}:[/underline]"
        )
        rprint()
        rprint(rescape(sugg.newCode))
        rprint("------\n")


def _print_completion(completion: ParsedChatCompletion[OptimizationSuite]):
    response = completion.choices[0].message
    rprint(f"[orange]Choice 1/{len(completion.choices)}[/orange]:")
    _print_message(response)
    if response.parsed is not None:
        _print_parsed_completion(response.parsed)
    if response.tool_calls:
        rprint("[blue]Tool calls:[/blue]")
        for call in response.tool_calls:
            funcname = call.function.name
            funcargs = call.function.arguments
            rprint(f"  {rescape(funcname)} =>", funcargs)


def smart_escape(thing: Any) -> Any:
    if type(thing) is str:
        return rescape(thing)
    else:
        return thing
