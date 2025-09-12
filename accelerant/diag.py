from multilspy.lsp_protocol_handler import lsp_types


class Diagnostic:
    is_error: bool
    filename: str
    start_line: int
    end_line: int
    message: str

    def __init__(
        self,
        is_error: bool,
        filename: str,
        start_line: int,
        end_line: int,
        message: str,
    ):
        self.is_error = is_error
        self.filename = filename
        self.start_line = start_line
        self.end_line = end_line
        self.message = message

    @staticmethod
    def from_lsp(d: "lsp_types.Diagnostic", fname: str) -> "Diagnostic":
        return Diagnostic(
            is_error=d["severity"] == lsp_types.DiagnosticSeverity.Error,
            filename=fname,
            start_line=d["range"]["start"]["line"] + 1,
            end_line=d["range"]["end"]["line"] + 1,
            message=d["message"],
        )

    def __eq__(self, other):
        if type(other) is type(self):
            return self.__members() == other.__members()
        return False

    def __hash__(self):
        return hash(self.__members())

    def __repr__(self) -> str:
        return (
            f"Diagnostic(is_error={self.is_error}, "
            f"filename={self.filename!r}, "
            f"start_line={self.start_line}, "
            f"end_line={self.end_line}, "
            f"message={self.message!r})"
        )

    def __members(self):
        return (
            self.is_error,
            self.filename,
            self.start_line,
            self.end_line,
            self.message,
        )
