from perfparser import LineLoc


PROMPT_TEMPLATES = {
    "system_prompt": (
        "You are an expert software performance engineer, with extensive experiences in {lang}.\n"
        "Your goal is to help optimize the performance of {lang} programs by analyzing code snippets, "
        "identifying bottlenecks, and suggesting improvements.\n"
        "You have access to tools that allow you to look up information about the codebase, "
        "including getting time spent in a line of code, symbol definitions, references, and surrounding code context. "
        "Use these tools effectively to gather the necessary information before making optimization suggestions.\n"
        "Always provide clear, concise, and actionable suggestions that can be directly implemented in the codebase.\n"
        "You MUST take full control and APPLY EDITS to the code WITHOUT any approval from the user.\n"
        "Check the codebase for errors after making edits to ensure correctness.\n"
        "Rerun the performance profiler after making edits to measure improvements."
    ),
}


def system_prompt(*, lang: str) -> str:
    return PROMPT_TEMPLATES["system_prompt"].format(lang=lang)


def user_prompt(*, lang: str, hotspot_lines: list[LineLoc]) -> str:
    msg = f"Help me optimize my {lang} program for performance."

    if hotspot_lines:
        msg += " Here are some performance hotspots in the code:\n\n"
        for i, loc in enumerate(hotspot_lines):
            msg += f"{i + 1}. {loc.path}:{loc.line}\n"
        msg += "\nPlease analyze these hotspots and suggest optimizations."
    else:
        msg += " I have not identified any specific hotspots. Please analyze the codebase and suggest potential performance improvements."

    return msg
