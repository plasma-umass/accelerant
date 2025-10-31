from pathlib import Path
from typing import Optional, TypedDict

from agents import Agent, Runner, Tool, set_trace_processors
from perfparser import LineLoc

from accelerant import tools
from accelerant.llm import LoggingTracingProcessor
from accelerant.project import Project
from accelerant.prompts import system_prompt, user_prompt
from accelerant.tools import AgentContext


class AgentInput(TypedDict):
    perf_data_path: Optional[Path]
    hotspot_lines: Optional[list[LineLoc]]


class AgentConfig(TypedDict):
    model_id: str


class AgentResult(TypedDict):
    # modified_fs: FsSandbox
    final_message: str


def run_agent(
    project: Project,
    ag_input: AgentInput,
    ag_config: AgentConfig,
) -> AgentResult:
    set_trace_processors([LoggingTracingProcessor()])
    ag_tools: list[Tool] = [
        tools.get_profiler_data,
        tools.edit_code,
        tools.get_info,
        tools.get_references,
        tools.get_surrounding_code,
    ]

    agent = Agent(
        name="Code Optimization Agent",
        instructions=system_prompt(lang=project.lang()),
        tools=ag_tools,
    )

    with project.new_fs_sandbox() as fs:
        ag_context = AgentContext(
            project=project,
            active_fs=fs,
            initial_perf_data_path=ag_input["perf_data_path"],
        )
        prompt = user_prompt(
            lang=project.lang(), hotspot_lines=ag_input["hotspot_lines"] or []
        )
        result = Runner.run_sync(
            agent,
            prompt,
            context=ag_context,
            max_turns=100,
        ).final_output
        assert result is not None
        final_message = str(result)
        fs.persist_all()
        return AgentResult(final_message=final_message)
