from typing import List, Optional


# Adapted from chatdbg.
def find_symbol(
    lines: List[str], lineno: int, symbol: str
) -> Optional[tuple[int, int]]:
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

    return (lineno, character)
