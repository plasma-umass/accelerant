from typing import List, Optional, TypedDict


class SymbolLoc(TypedDict):
    line_idx: int
    start_chr: int
    end_chr: int  # inclusive


# Adapted from chatdbg.
def find_symbol(lines: List[str], lineno: int, symbol: str) -> Optional[SymbolLoc]:
    # We just return the first match here. Maybe we should find all definitions.
    character = lines[lineno].find(symbol)

    # Now, some heuristics to make up for GPT's terrible math skills.
    if character == -1:
        symbol = symbol.lstrip("*")
        character = lines[lineno].find(symbol)

    if character == -1:
        symbol = symbol.split("::")[-1]
        character = lines[lineno].find(symbol)

    # Check five lines above and below.
    if character == -1:
        for i in range(-5, 6, 1):
            if lineno + i < 0 or lineno + i >= len(lines):
                continue
            character = lines[lineno + i].find(symbol)
            if character != -1:
                lineno += i
                break

    if character == -1:
        return None

    assert len(symbol) > 0

    return {
        "line_idx": lineno,
        "start_chr": character,
        "end_chr": character + len(symbol) - 1,
    }


def truncate_for_llm(text: str, char_limit: int):
    if len(text) > char_limit:
        return text[:char_limit] + "[...too long...]"
    return text
