from multilspy.lsp_protocol_handler import lsp_types


from pathlib import Path
from typing import List, Optional

from accelerant.fs_sandbox import FsSandbox
from accelerant.lsp import LSP


class Project:
    _root: Path
    _lang: str
    _lsp: Optional[LSP]

    def __init__(self, root, lang):
        self._root = root
        self._lang = lang
        self._lsp = None

    def lsp(self) -> LSP:
        if self._lsp is None:
            self._lsp = LSP(self._root, self._lang)
        return self._lsp

    def fs_sandbox(self) -> FsSandbox:
        return FsSandbox(self._root)

    def get_line(self, filename: str, line: int) -> str:
        assert line >= 0
        return self.get_lines(filename, line, line)[0]

    def get_lines(
        self, filename: str, sline: Optional[int] = None, eline: Optional[int] = None
    ) -> List[str]:
        with open(self._root.joinpath(filename), "r") as f:
            lines = list(map(lambda s: s.rstrip(), f.readlines()))
            sline = max(sline or 0, 0)
            maxline = len(lines) - 1
            eline = min(eline or maxline, maxline)
            return lines[sline : eline + 1]

    def get_range(self, filename: str, lsp_range: lsp_types.Range) -> List[str]:
        """Return lines covered by an LSP Range.

        LSP ranges are [start, end) by position. For a line-based slice, we include
        the end line unless end.character == 0, in which case the end line is exclusive.
        """
        start_line = lsp_range["start"]["line"]
        end_line = lsp_range["end"]["line"]
        if lsp_range["end"]["character"] == 0:
            end_line -= 1
        return self.get_lines(filename, start_line, end_line)

    def lang(self) -> str:
        return self._lang
