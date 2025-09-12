import asyncio
from contextlib import contextmanager
import os
from pathlib import Path, PurePath
from typing import Any, Coroutine, Optional, TypeGuard, TypedDict, Iterator

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_utils import PathUtils
from multilspy.lsp_protocol_handler import lsp_types
from multilspy.lsp_protocol_handler.lsp_types import RelatedFullDocumentDiagnosticReport
from multilspy.lsp_protocol_handler.server import LanguageServerHandler
from multilspy import multilspy_types


class LSP:
    _lsp: SyncLanguageServer
    _root: Path
    _lang: str

    def __init__(self, root: Path, lang: str):
        config = MultilspyConfig.from_dict({"code_language": lang})
        logger = MultilspyLogger()
        self._lsp = SyncLanguageServer.create(config, logger, str(root))
        self._root = root
        self._lang = lang

    @contextmanager
    def start_server(self) -> Iterator[None]:
        with self._lsp.start_server():
            yield

    def syncexec[T](self, coroutine: Coroutine[Any, Any, T]) -> T:
        assert self._lsp.loop is not None
        return asyncio.run_coroutine_threadsafe(coroutine, self._lsp.loop).result()

    async def request_hover(
        self, relpath: str, line: int, column: int
    ) -> Optional[multilspy_types.Hover]:
        return await self._lsp.language_server.request_hover(relpath, line, column)

    async def request_references(
        self, relpath: str, line: int, column: int
    ) -> list[multilspy_types.Location]:
        return await self._lsp.language_server.request_references(relpath, line, column)

    async def request_definition_full(self, relpath: str, line: int, column: int):
        with self._lsp.open_file(relpath):
            uri = self.to_uri(relpath)
            response = await self._srv().send.definition(
                {
                    "textDocument": {"uri": uri},
                    "position": {
                        "line": line,
                        "character": column,
                    },
                }
            )
            return response

    async def request_document_diagnostics(
        self, relpath: str
    ) -> RelatedFullDocumentDiagnosticReport:
        with self._lsp.open_file(relpath):
            uri = self.to_uri(relpath)
            self._srv().notify.did_save_text_document({"textDocument": {"uri": uri}})
            response = await self._srv().send.text_document_diagnostic(
                {"textDocument": {"uri": uri}}
            )
            assert response["kind"] == "full"
            return response

    async def request_document_symbols(
        self, relpath: str
    ) -> list[lsp_types.DocumentSymbol] | list[lsp_types.SymbolInformation]:
        """Fetch document symbols for a file.

        Servers may return either DocumentSymbol[] (hierarchical) or SymbolInformation[] (flat).
        """
        with self._lsp.open_file(relpath):
            uri = self.to_uri(relpath)
            params: lsp_types.DocumentSymbolParams = {"textDocument": {"uri": uri}}
            resp = await self._srv().send.document_symbol(params)
            return resp or []

    async def request_nearest_parent_symbol(
        self, relpath: str, line_zero_based: int
    ) -> Optional["LiteSymbol"]:
        """Fetch document symbols and return the nearest parent symbol for a line.

        Returns a normalized TypedDict with the symbol name and its LSP Range.
        """
        symbols = await self.request_document_symbols(relpath)
        if _is_document_symbol_list(symbols):
            ds = find_nearest_parent_from_document_symbols(symbols, line_zero_based)
            if ds is None:
                return None
            return {"name": ds["name"], "range": ds["range"]}
        elif _is_symbol_information_list(symbols):
            si = find_nearest_parent_from_symbol_information(symbols, line_zero_based)
            if si is None:
                return None
            return {"name": si["name"], "range": si["location"]["range"]}
        else:
            return None

    def to_uri(self, relpath: str) -> str:
        return relpath_to_uri(relpath, str(self._root))

    def _srv(self) -> LanguageServerHandler:
        return self._lsp.language_server.server


def relpath_to_uri(relpath: str, root: str) -> str:
    return Path(str(PurePath(root, relpath))).as_uri()


def uri_to_relpath(uri: str, root: str) -> str:
    absolutePath = PathUtils.uri_to_path(uri)
    relativePath = str(PurePath(os.path.relpath(absolutePath, root)))
    return relativePath


def line_in_lsp_range(line_zero_based: int, r: lsp_types.Range) -> bool:
    """Check if a 0-based line is inside an LSP Range.

    LSP ranges are [start, end) by position; when we only have line, treat the end
    line as exclusive if end.character == 0, otherwise inclusive.
    """
    s = r["start"]
    e = r["end"]
    sL = s["line"]
    eL = e["line"]
    if line_zero_based < sL or line_zero_based > eL:
        return False
    if line_zero_based == eL:
        eC = e["character"]
        if eC == 0:
            return False
    return True


def find_nearest_parent_from_document_symbols(
    symbols: list[lsp_types.DocumentSymbol], line_zero_based: int
) -> Optional[lsp_types.DocumentSymbol]:
    """Return the smallest DocumentSymbol whose range contains the given 0-based line.

    Uses hierarchical children to find the nearest (smallest-span) containing symbol.
    """
    best: Optional[lsp_types.DocumentSymbol] = None
    best_span: Optional[int] = None

    def visit(sym: lsp_types.DocumentSymbol) -> None:
        nonlocal best, best_span
        rng = sym["range"]
        if not line_in_lsp_range(line_zero_based, rng):
            return
        start = rng["start"]["line"]
        end = rng["end"]["line"]
        span = max(0, end - start)
        if best is None or span < (best_span or 10**9):
            best = sym
            best_span = span
        children = sym.get("children")
        if children:
            for child in children:
                visit(child)

    for s in symbols:
        visit(s)
    return best


def find_nearest_parent_from_symbol_information(
    symbols: list[lsp_types.SymbolInformation], line_zero_based: int
) -> Optional[lsp_types.SymbolInformation]:
    """Return the smallest SymbolInformation whose range contains the given 0-based line."""
    best: Optional[lsp_types.SymbolInformation] = None
    best_span: Optional[int] = None
    for sym in symbols:
        rng = sym["location"]["range"]
        if not line_in_lsp_range(line_zero_based, rng):
            continue
        start = rng["start"]["line"]
        end = rng["end"]["line"]
        span = max(0, end - start)
        if best is None or span < (best_span or 10**9):
            best = sym
            best_span = span
    return best


def _is_document_symbol_list(
    syms: list[lsp_types.DocumentSymbol] | list[lsp_types.SymbolInformation],
) -> TypeGuard[list[lsp_types.DocumentSymbol]]:
    # Heuristic: DocumentSymbol has 'selectionRange' while SymbolInformation has 'location'
    return bool(syms) and "selectionRange" in syms[0]


def _is_symbol_information_list(
    syms: list[lsp_types.DocumentSymbol] | list[lsp_types.SymbolInformation],
) -> TypeGuard[list[lsp_types.SymbolInformation]]:
    # Heuristic: SymbolInformation has 'location' while DocumentSymbol does not
    return bool(syms) and "location" in syms[0]


class LiteSymbol(TypedDict):
    name: str
    range: lsp_types.Range
