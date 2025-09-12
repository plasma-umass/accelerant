from pathlib import PurePath
from typing import List, Union

from multilspy.lsp_protocol_handler import lsp_types

from accelerant.chat_interface import CodeSuggestion
from accelerant.lsp import find_range_by_name
from accelerant.project import Project


def apply_simultaneous_suggestions(
    suggestions: List[CodeSuggestion],
    project: Project,
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
        # FIXME: handle conflicting suggestions (i.e. that overlap)
        symbols = project.lsp().syncexec(
            project.lsp().request_document_symbols(relpath)
        )
        suggs = list(
            map(lambda s: get_symbol_range_for_suggestion(symbols, s), suggs_raw)
        )
        suggs = list(sorted(suggs, key=lambda s: s[0]["start"]["line"]))
        abspath = PurePath(project._root, relpath)
        with open(abspath, "r") as f:
            old_lines = enumerate(f.readlines())

        print(abspath, suggs)
        with open(abspath, "w") as f:
            skip_until_after = 0
            for old_num, old_line in old_lines:
                if old_num <= skip_until_after:
                    continue
                if suggs and suggs[0][0]["start"]["line"] == old_num:
                    print("apply")
                    sugg = suggs[0]
                    suggs = suggs[1:]
                    f.write(sugg[1])
                    if not sugg[1].endswith("\n"):
                        f.write("\n")
                    skip_until_after = sugg[0]["end"]["line"]
                else:
                    f.write(old_line)


def get_symbol_range_for_suggestion(
    symbols: Union[list[lsp_types.DocumentSymbol], list[lsp_types.SymbolInformation]],
    s: CodeSuggestion,
) -> tuple[lsp_types.Range, str]:
    rng = find_range_by_name(symbols, s.regionName)
    assert rng is not None
    return (rng, s.newCode)
