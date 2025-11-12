import base64
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile
import re


def make_flamegraph_png(perf_data_path: Path) -> bytes:
    svg_str = make_flamegraph_svg(perf_data_path)
    png_data = svg_to_png(svg_str)
    return png_data


def make_flamegraph_svg(perf_data_path: Path) -> str:
    with NamedTemporaryFile(suffix=".svg") as output_svg_temp:
        subprocess.run(
            [
                "flamegraph",
                "--perfdata",
                perf_data_path,
                "--output",
                output_svg_temp.name,
            ],
            check=True,
        )
        output_svg_temp.seek(0)
        svg_data = output_svg_temp.read().decode()
    return svg_data


def svg_to_png(svg_str: str) -> bytes:
    # HACK: resvg doesn't understand the monospace font-family, so replace it with concrete fonts
    svg_str = re.sub(
        "font-family: ?monospace",
        "font-family: 'Fira Mono', 'DejaVu Sans Mono', 'Ubuntu Mono'",
        svg_str,
    )
    with NamedTemporaryFile(suffix=".svg") as svg_temp:
        svg_temp.write(svg_str.encode())
        svg_temp.flush()
        with NamedTemporaryFile(suffix=".png") as png_temp:
            subprocess.run(
                ["resvg", "--zoom=2", svg_temp.name, png_temp.name],
                check=True,
            )
            png_temp.seek(0)
            png_data = png_temp.read()
    return png_data


def png_to_data_url(png_data: bytes) -> str:
    b64_encoded = base64.b64encode(png_data).decode()
    data_url = f"data:image/png;base64,{b64_encoded}"
    return data_url
