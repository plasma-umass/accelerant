from agents import TracingProcessor
from rich import print


class LoggingTracingProcessor(TracingProcessor):
    def __init__(self):
        self.active_traces = {}
        self.active_spans = {}

    def on_trace_start(self, trace):
        print(f"[bold green]Starting trace:[/bold green] {trace.name}")
        self.active_traces[trace.trace_id] = trace

    def on_trace_end(self, trace):
        print(f"[bold red]Ending trace:[/bold red] {trace.name}")
        del self.active_traces[trace.trace_id]

    def on_span_start(self, span):
        print(f"[blue]Starting span:[/blue] {span.span_data.export()}")
        self.active_spans[span.span_id] = span

    def on_span_end(self, span):
        print(f"[magenta]Ending span:[/magenta] {span.span_data.export()}")
        del self.active_spans[span.span_id]

    def shutdown(self):
        self.active_traces.clear()
        self.active_spans.clear()

    def force_flush(self):
        pass
