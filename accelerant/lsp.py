import asyncio
import os
from pathlib import Path, PurePath
from typing import Any, Coroutine
from multilspy import LanguageServer, SyncLanguageServer
from multilspy.multilspy_utils import PathUtils


async def request_definition_full(
    lsp: LanguageServer, relative_file_path: str, line: int, column: int
):
    with lsp.open_file(relative_file_path):
        uri = relpath_to_uri(relative_file_path, lsp.repository_root_path)
        response = await lsp.server.send.definition(
            {
                "textDocument": {"uri": uri},
                "position": {
                    "line": line,
                    "character": column,
                },
            }
        )
        return response


async def request_document_diagnostics(lsp: LanguageServer, relpath: str):
    with lsp.open_file(relpath):
        uri = relpath_to_uri(relpath, lsp.repository_root_path)
        lsp.server.notify.did_save_text_document({"textDocument": {"uri": uri}})
        return await lsp.server.send.text_document_diagnostic(
            {"textDocument": {"uri": uri}}
        )


def relpath_to_uri(relpath: str, root: str) -> str:
    return Path(str(PurePath(root, relpath))).as_uri()


def uri_to_relpath(uri: str, root: str) -> str:
    absolutePath = PathUtils.uri_to_path(uri)
    relativePath = str(PurePath(os.path.relpath(absolutePath, root)))
    return relativePath


def syncexec[T](lsp: SyncLanguageServer, coroutine: Coroutine[Any, Any, T]) -> T:
    assert lsp.loop is not None
    return asyncio.run_coroutine_threadsafe(coroutine, lsp.loop).result()
