import json
from rich.markup import escape as rescape
from typing import Any, List, Optional
from llm_utils import number_group_of_lines
import openai
from openai import NotGiven
from openai.types.chat import (
    ChatCompletionDeveloperMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ParsedChatCompletion,
)
from rich import print as rprint

from accelerant.chat_interface import (
    CodeSuggestion,
    ErrorFixingSuggestions,
    ProjectAnalysis,
    OptimizationSuite,
)
from accelerant.diag import Diagnostic
from accelerant.lsp import sync_request_document_diagnostics
from accelerant.patch import apply_simultaneous_suggestions
from accelerant.perf import PerfData
from accelerant.project import Project
from accelerant.tools import (
    GetInfoTool,
    GetReferencesTool,
    GetSurroundingCodeTool,
    LLMToolRunner,
)
from perfparser import LineLoc


def optimize_locations(
    project: Project, locs: List[LineLoc], perf_data: Optional[PerfData], model_id: str
) -> str:
    lang = project.lang()

    try:
        client = openai.OpenAI(timeout=90)
    except openai.OpenAIError:
        print("you need an OpenAI key to use this tool.")
        print("You can get a key here: https://platform.openai.com/api-keys.")
        print("set the environment variable OPENAI_API_KEY to your key value.")
        raise Exception()

    tool_runner = LLMToolRunner(
        project,
        [
            GetInfoTool(),
            GetReferencesTool(),
            GetSurroundingCodeTool(),
        ],
    )

    analysis_req_msg = "I've identified the following lines as performance hotspots. Please explore the code and try to understand what is happening and why it is slow. Do NOT give suggestions at this point; just reason about what's happening. BRIEFLY explain anything that could lead to poor performance.\n\n"
    for index, loc in enumerate(locs):
        filename, lineno = loc.path, loc.line
        pct_time = perf_data.lookup_pct_time(loc) if perf_data is not None else None
        pct_time_s = (
            f" ({pct_time:.0%} of all program time)" if pct_time is not None else ""
        )
        prettyline = number_group_of_lines(
            project.get_lines(filename, lineno - 1 - 5, lineno - 1 + 5),
            max(lineno - 5, 1),
        )
        analysis_req_msg += f"# {index + 1}. {filename}:{lineno}{pct_time_s}\n\n```{lang}\n{prettyline}\n```\n\n"

    messages: List[ChatCompletionMessageParam] = [
        _make_system_message(
            model_id,
            f"You are a {lang} performance optimization assistant. You NEVER make assumptions or express hypotheticals about what the user's program does. Instead, you make ample use of the tool calls available to you to thoroughly explore the user's program.",
        ),
        {"role": "user", "content": analysis_req_msg},
    ]
    _, analysis = run_chat(
        messages, client, model_id, tool_runner, response_format=ProjectAnalysis
    )
    assert analysis is not None

    sugg_req_msg = "I've identified the following lines as performance hotspots. Please help me optimize them.\n\n"
    for index, region in enumerate(analysis.regions):
        filename, lineno = region.filename, region.line
        pct_time = (
            perf_data.lookup_pct_time(LineLoc(filename, lineno))
            if perf_data is not None
            else None
        )
        pct_time_s = (
            f" ({pct_time:.0%} of all program time)" if pct_time is not None else ""
        )
        prettyline = number_group_of_lines(
            project.get_lines(filename, lineno - 1 - 5, lineno - 1 + 5),
            max(lineno - 5, 1),
        )
        sugg_req_msg += f"# {index + 1}. {filename}:{lineno}{pct_time_s}\n\n```{lang}\n{prettyline}\n```\n\n{region.performanceAnalysis}\n\n"

    messages = [
        _make_system_message(
            model_id,
            f"You are a {lang} performance optimization assistant. You NEVER make assumptions or express hypotheticals about what the user's program does. Instead, you make ample use of the tool calls available to you to thoroughly explore the user's program. You always give CONCRETE code suggestions.",
        ),
        {"role": "user", "content": sugg_req_msg},
    ]
    sugg_str, opt_suite = run_chat(
        messages, client, model_id, tool_runner, response_format=OptimizationSuite
    )
    assert opt_suite

    apply_suggestions_until_error_fixpoint(
        opt_suite.suggestions, client, model_id, project, tool_runner
    )

    return sugg_str


def apply_suggestions_until_error_fixpoint(
    suggs: List[CodeSuggestion],
    client: openai.OpenAI,
    model_id: str,
    project: Project,
    tool_runner: LLMToolRunner,
    max_rounds=2,
):
    round_idx = 0
    # Use <= since we still want to check the LLM suggestions,
    # even if we won't end up going back to the LLM if they're wrong.
    while round_idx <= max_rounds:
        apply_simultaneous_suggestions(suggs, project)
        # TODO: collect diagnostics from all files, then feed them back to LLM
        # FIXME: how to get diagnostics from files that depend on these files
        # but weren't themselves changed?
        changed_files = set(map(lambda s: s.filename, suggs))
        diags = (
            Diagnostic.from_lsp(diag, fname)
            for fname in changed_files
            for diag in sync_request_document_diagnostics(project.lsp(), fname)["items"]
        )
        errors = list(set(filter(lambda d: d.is_error, diags)))
        rprint("Errors:", errors)
        if not errors:
            return True
        if round_idx == max_rounds:
            # Still errors, but we've reached the round limit
            return False

        fix_req_msg = "My program has the following errors. Please fix them for me.\n\n"
        for error in errors:
            fix_req_msg += f"- In {error.filename}:{error.start_line}-{error.end_line}: {error.message}\n"

        messages: List[ChatCompletionMessageParam] = [
            _make_system_message(
                model_id,
                f"You are a {project.lang()} error-fixing assistant. You NEVER make assumptions or express hypotheticals about what the user's program does. Instead, you make ample use of the tool calls available to you to thoroughly explore the user's program. You always give CONCRETE code suggestions.",
            ),
            {"role": "user", "content": fix_req_msg},
        ]
        _, fix_suite = run_chat(
            messages,
            client,
            model_id,
            tool_runner,
            response_format=ErrorFixingSuggestions,
        )
        assert fix_suite
        suggs = fix_suite.suggestions

    return False


def run_chat[RespFormat](
    messages: List[ChatCompletionMessageParam],
    client: openai.OpenAI,
    model_id: str,
    tool_runner: LLMToolRunner,
    response_format: type[RespFormat] | NotGiven,
) -> tuple[str, Optional[RespFormat]]:
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
            response_format=response_format,
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

    assert response_msg is not None and response_msg.content is not None
    return response_msg.content, response_msg.parsed


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


def _print_project_analysis(analysis: ProjectAnalysis):
    rprint("[underline]Project Analysis[/underline]")
    rprint()

    for region in analysis.regions:
        rprint(f"[underline]{rescape(region.filename)}:{region.line}[/underline]")
        rprint()
        rprint(rescape(region.performanceAnalysis))
        rprint("------\n")


def _print_optimization_suite(parsed: OptimizationSuite):
    rprint("[underline]High-level Summary[/underline]")
    rprint(rescape(parsed.highLevelSummary))
    rprint()

    for sugg in parsed.suggestions:
        _print_code_suggestions(sugg)


def _print_error_fixing_suggestions(parsed: ErrorFixingSuggestions):
    rprint("[underline]Error-Fixing Suggestions[/underline]")
    rprint()

    for sugg in parsed.suggestions:
        _print_code_suggestions(sugg)


def _print_code_suggestions(sugg: CodeSuggestion):
    rprint(
        f"[underline]In {rescape(sugg.filename)}, replace lines {sugg.startLine} to {sugg.endLine}:[/underline]"
    )
    rprint()
    rprint(rescape(sugg.newCode))
    rprint("------\n")


def _print_completion[T](completion: ParsedChatCompletion[T]):
    response = completion.choices[0].message
    rprint(f"[orange]Choice 1/{len(completion.choices)}[/orange]:")
    _print_message(response)
    if response.parsed is not None:
        if type(response.parsed) is ProjectAnalysis:
            _print_project_analysis(response.parsed)
        elif type(response.parsed) is OptimizationSuite:
            _print_optimization_suite(response.parsed)
        elif type(response.parsed) is ErrorFixingSuggestions:
            _print_error_fixing_suggestions(response.parsed)
        else:
            rprint("[red]unknown structured format[/red]")
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
