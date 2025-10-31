from pathlib import Path, PurePath
from typing import List, Union

from multilspy.lsp_protocol_handler import lsp_types

from accelerant.chat_interface import CodeSuggestion
from accelerant.fs_sandbox import FsSandbox
from accelerant.lsp import find_range_by_name
from accelerant.project import Project


def apply_simultaneous_suggestions(
    project: Project,
    fs: FsSandbox,
    suggestions: List[CodeSuggestion],
):
    """
    Apply suggestions that were created to be applied simultaneously.
    In other words, they don't account for changes in line numbers caused by
    other suggestions.
    """
    by_file: dict[str, List[CodeSuggestion]] = {}
    for sugg_ in suggestions:
        if sugg_.filename not in by_file:
            by_file[sugg_.filename] = []
        by_file[sugg_.filename].append(sugg_)

    for relpath, suggs_raw in by_file.items():
        abspath = PurePath(project._root, relpath)
        old_text = FsSandbox.read_file(fs, Path(abspath))
        old_lines = old_text.splitlines(keepends=True)

        line_starts = [0]
        for line in old_lines:
            last = line_starts[-1]
            line_starts.append(last + len(line))

        # FIXME: handle conflicting suggestions (i.e. that overlap)
        symbols = project.lsp().syncexec(
            project.lsp().request_document_symbols(relpath)
        )
        rng_to_offset = lambda loc: (  # noqa: E731
            line_starts[loc["start"]["line"]] + loc["start"]["character"],
            line_starts[loc["end"]["line"]] + loc["end"]["character"],
        )
        suggs = list(
            map(
                lambda tup: (rng_to_offset(tup[0]), tup[1]),
                map(
                    lambda s: (get_symbol_range_for_suggestion(symbols, s), s.new_code),
                    suggs_raw,
                ),
            )
        )
        suggs = list(sorted(suggs, key=lambda tup: tup[0][1], reverse=True))

        new_text = []
        cur_end = len(old_text)
        while suggs:
            sugg = suggs[0]
            suggs = suggs[1:]
            if sugg[0][1] + 1 < cur_end:
                new_text.append(old_text[sugg[0][1] + 1 : cur_end])
            new_text.append(sugg[1])
            cur_end = sugg[0][0]
        new_text.append(old_text[0:cur_end])

        fs.write_file(Path(abspath), "".join(reversed(new_text)))


def get_symbol_range_for_suggestion(
    symbols: Union[list[lsp_types.DocumentSymbol], list[lsp_types.SymbolInformation]],
    s: CodeSuggestion,
) -> lsp_types.Range:
    rng = find_range_by_name(symbols, s.region_name)
    assert rng is not None, f"Could not find symbol {s.region_name}"
    return rng
