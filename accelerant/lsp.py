import asyncio
import os
from pathlib import Path, PurePath
from typing import Any, Coroutine
from multilspy import LanguageServer, SyncLanguageServer
from multilspy.multilspy_utils import PathUtils

from accelerant.project import Project


async def request_definition_full(
    lsp: LanguageServer, relative_file_path: str, line: int, column: int
):
    with lsp.open_file(relative_file_path):
        response = await lsp.server.send.definition(
            {
                "textDocument": {
                    "uri": Path(
                        str(PurePath(lsp.repository_root_path, relative_file_path))
                    ).as_uri()
                },
                "position": {
                    "line": line,
                    "character": column,
                },
            }
        )
        return response


def extract_relative_path(uri: str, project: Project) -> str:
    absolutePath = PathUtils.uri_to_path(uri)
    relativePath = str(PurePath(os.path.relpath(absolutePath, project._root)))
    return relativePath


def syncexec[T](lsp: SyncLanguageServer, coroutine: Coroutine[Any, Any, T]) -> T:
    assert lsp.loop is not None
    return asyncio.run_coroutine_threadsafe(coroutine, lsp.loop).result()
