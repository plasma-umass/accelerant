from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


from pathlib import Path
from typing import List, Optional


class Project:
    _root: Path
    _lang: str
    _lsp: Optional[SyncLanguageServer]

    def __init__(self, root, lang):
        self._root = root
        self._lang = lang
        self._lsp = None

    def lsp(self) -> SyncLanguageServer:
        if self._lsp is None:
            config = MultilspyConfig.from_dict({"code_language": self._lang})
            logger = MultilspyLogger()
            self._lsp = SyncLanguageServer.create(config, logger, str(self._root))
        return self._lsp

    def get_line(self, filename: str, line: int) -> str:
        assert line >= 0
        return self.get_lines(filename, line, line)[0]

    def get_lines(
        self, filename: str, sline: Optional[int] = None, eline: Optional[int] = None
    ) -> List[str]:
        with open(self._root.joinpath(filename), "r") as f:
            lines = f.readlines()
            sline = max(sline or 0, 0)
            maxline = len(lines) - 1
            eline = min(eline or maxline, maxline)
            return lines[sline : eline + 1]
