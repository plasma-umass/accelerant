from pathlib import PurePath
from typing import List

from accelerant.chat_interface import CodeSuggestion
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
    for sugg in suggestions:
        if sugg.filename not in by_file:
            by_file[sugg.filename] = []
        by_file[sugg.filename].append(sugg)

    for relpath, suggs in by_file.items():
        abspath = PurePath(project._root, relpath)
        # FIXME: handle conflicting suggestions (i.e. that overlap)
        suggs = list(sorted(suggs, key=lambda s: s.startLine))
        with open(abspath, "r") as f:
            old_lines = enumerate(f.readlines(), start=1)

        print(abspath, suggs)
        with open(abspath, "w") as f:
            skip_until_after = 0
            for old_num, old_line in old_lines:
                if old_num <= skip_until_after:
                    continue
                if suggs and suggs[0].startLine == old_num:
                    print("apply")
                    sugg = suggs[0]
                    suggs = suggs[1:]
                    f.write(sugg.newCode)
                    if not sugg.newCode.endswith("\n"):
                        f.write("\n")
                    skip_until_after = sugg.endLine
                else:
                    f.write(old_line)
