import json
from agents import TracingProcessor
from rich import print


class LoggingTracingProcessor(TracingProcessor):
    def __init__(
        self,
    ):
        pass

    def on_trace_start(self, trace):
        pass

    def on_trace_end(self, trace):
        pass

    def on_span_start(self, span):
        data = span.span_data.export()
        if data["type"] == "agent":
            print(f"[bold blue]Starting[/bold blue] agent: {data.get('name', '')}")
        elif data["type"] == "response":
            print("[bold blue]Generating[/bold blue] response...")
        elif data["type"] == "function":
            print(f"[bold blue]Invoking[/bold blue] function: {data.get('name', '')}")
        else:
            print(f"[bold blue]Starting[/bold blue] span of type: {data['type']}")

    def on_span_end(self, span):
        data = span.span_data.export()
        if data["type"] == "agent":
            print(f"[bold green]Finished[/bold green] agent: {data.get('name', '')}")
        elif data["type"] == "response":
            print("[bold green]Completed[/bold green] generating response.")
        elif data["type"] == "function":
            print(
                f"[bold green]Completed[/bold green] invoking function: {data.get('name', '')}"
            )
            print("[u]Inputs:[/u]")
            inputs = json.loads(data.get("input", "{}") or "{}")
            for inp_name, inp_value in inputs.items():
                print(f"  [bold]{inp_name}:[/bold] {inp_value}")
            print("[u]Output:[/u]")
            output = data.get("output", "") or ""
            try:
                parsed_output = json.loads(output)
                print(f"  {parsed_output}")
            except json.JSONDecodeError:
                print(f"  {output}")
        else:
            print(f"[bold green]Finished[/bold green] span of type: {data['type']}")

    def shutdown(self):
        pass

    def force_flush(self):
        pass
