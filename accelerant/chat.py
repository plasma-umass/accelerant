from rich.markup import escape as rescape
from typing import Any, List, Optional
from agents import Agent, Runner, Tool, TracingProcessor, set_trace_processors
from rich import print as rprint

from accelerant.chat_interface import (
    CodeSuggestion,
    ProjectAnalysis,
    OptimizationSuite,
)
from accelerant.fs_sandbox import FsSandbox
from accelerant.lsp import TOP_LEVEL_SYMBOL_KINDS
from accelerant.patch import apply_simultaneous_suggestions
from accelerant.perf import PerfData
from accelerant.project import Project
from accelerant import tools
from accelerant.util import custom_number_group_of_lines
from perfparser import LineLoc


def _build_hotspot_prompt(
    project: Project,
    lang: str,
    items: list[tuple[str, int, Optional[str]]],
    perf_data: Optional[PerfData],
    intro: str,
) -> str:
    """Construct a hotspot prompt with optional per-item extra text.

    items: list of (filename, line, extra_text)
    extra_text is appended after the code block when present.
    """
    msg = intro + "\n\n"
    for index, (filename, lineno, extra_text) in enumerate(items):
        pct_time = (
            perf_data.lookup_pct_time(LineLoc(filename, lineno))
            if perf_data is not None
            else None
        )
        pct_time_s = (
            f" ({pct_time:.0%} of all program time)" if pct_time is not None else ""
        )

        parent_sym = project.lsp().syncexec(
            project.lsp().request_nearest_parent_symbol(
                filename, lineno - 1, TOP_LEVEL_SYMBOL_KINDS
            ),
        )
        # FIXME: avoid crashing
        assert parent_sym is not None
        sline = parent_sym["range"]["start"]["line"]
        prettyline = custom_number_group_of_lines(
            project.get_range(filename, parent_sym["range"]),
            max(sline + 1, 1),
            with_note=lambda n: " <--- HOTSPOT" if n == lineno else "",
        )

        msg += (
            f"#{index + 1}. {filename} at region {parent_sym['name']} {pct_time_s}\n\n"
            f"```{lang}\n{prettyline}\n```\n\n"
        )
        if extra_text:
            msg += f"{extra_text}\n\n"
    return msg


def optimize_locations(
    project: Project,
    fs: FsSandbox,
    locs: List[LineLoc],
    perf_data: Optional[PerfData],
    model_id: str,
) -> str:
    set_trace_processors([LoggingTracingProcessor()])

    lang = project.lang()

    agent_context = tools.AgentContext(project=project)
    agent_tools: list[Tool] = [
        tools.get_info,
        tools.get_references,
        tools.get_surrounding_code,
    ]

    analysis_system_message = f"You are a {lang} performance optimization assistant. You NEVER make assumptions or express hypotheticals about what the user's program does. Instead, you make ample use of the tool calls available to you to thoroughly explore the user's program."
    analysis_intro = "I've identified the following lines as performance hotspots. Please explore the code and try to understand what is happening and why it is slow. Do NOT give suggestions at this point; just reason about what's happening. BRIEFLY explain anything that could lead to poor performance."
    analysis_items: list[tuple[str, int, Optional[str]]] = [
        (loc.path, loc.line, None) for loc in locs if loc.line > 0
    ]
    analysis_req_msg = _build_hotspot_prompt(
        project, lang, analysis_items, perf_data, analysis_intro
    )
    analysis_agent = Agent(
        name="Performance Analysis Assistant",
        instructions=analysis_system_message,
        output_type=ProjectAnalysis,
        tools=agent_tools,
    )
    analysis = Runner.run_sync(
        analysis_agent, analysis_req_msg, context=agent_context
    ).final_output
    assert analysis is not None

    sugg_system_message = f"You are a {lang} performance optimization assistant. You NEVER make assumptions or express hypotheticals about what the user's program does. Instead, you make ample use of the tool calls available to you to thoroughly explore the user's program. You always give CONCRETE code suggestions. NEVER delete code comments or gratuitously rename variables."
    sugg_intro = "I've identified the following lines as performance hotspots. Please help me optimize them."
    sugg_items: list[tuple[str, int, Optional[str]]] = [
        (region.filename, region.line, region.performanceAnalysis)
        for region in analysis.regions
    ]
    sugg_req_msg = _build_hotspot_prompt(
        project, lang, sugg_items, perf_data, sugg_intro
    )
    sugg_agent = Agent(
        name="Code Optimization Assistant",
        instructions=sugg_system_message,
        output_type=OptimizationSuite,
        tools=agent_tools,
    )
    opt_suite = Runner.run_sync(
        sugg_agent, sugg_req_msg, context=agent_context
    ).final_output
    assert opt_suite

    apply_simultaneous_suggestions(project, fs, opt_suite.suggestions)

    return opt_suite.highLevelSummary


class LoggingTracingProcessor(TracingProcessor):
    def __init__(self):
        self.active_traces = {}
        self.active_spans = {}

    def on_trace_start(self, trace):
        rprint(f"[bold green]Starting trace:[/bold green] {trace.name}")
        self.active_traces[trace.trace_id] = trace

    def on_trace_end(self, trace):
        rprint(f"[bold red]Ending trace:[/bold red] {trace.name}")
        del self.active_traces[trace.trace_id]

    def on_span_start(self, span):
        rprint(f"[blue]Starting span:[/blue] {span.span_data.export()}")
        self.active_spans[span.span_id] = span

    def on_span_end(self, span):
        rprint(f"[magenta]Ending span:[/magenta] {span.span_data.export()}")
        del self.active_spans[span.span_id]

    def shutdown(self):
        self.active_traces.clear()
        self.active_spans.clear()

    def force_flush(self):
        pass


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


def _print_code_suggestions(sugg: CodeSuggestion):
    rprint(
        f"[underline]In {rescape(sugg.filename)}, replace region `{rescape(sugg.regionName)}`:[/underline]"
    )
    rprint()
    rprint(rescape(sugg.newCode))
    rprint("------\n")


def smart_escape(thing: Any) -> Any:
    if type(thing) is str:
        return rescape(thing)
    else:
        return thing
