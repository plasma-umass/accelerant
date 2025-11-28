# Accelerant

## Setup

Prerequisites: Accelerant is currently designed for use on x86 Linux.

1. Git clone
2. Install [`uv`](https://github.com/astral-sh/uv) if not already installed
3. Install Linux `perf`
4. If you want support for sending flamegraphs to the LLM:
    a. `cargo install flamegraph`
    a. `cargo install resvg`

## Basic usage

First, run `sudo sh -c 'echo 1 >/proc/sys/kernel/perf_event_paranoid'` to get
more accurate profiling of code that (transitively) uses syscalls.

In the `accelerant` repository, run:

```console
$ uv run accelerant_server.py
```

In a separate terminal, run:

```console
$ curl 'http://127.0.0.1:5000/optimize?project=PATH_TO_PROJECT_ROOT&targetBinary=target/release/REST_OF_PATH_TO_EXECUTABLE_TO_OPTIMIZE'
```

Accelerant will automatically build, run, and profile your project using `cargo` and `perf`.

If you've already run the `perf` profiler and collected a `perf.data` file, you can give it to Accelerant by appending a `perfDataPath` query parameter with the path to the file.

Also, if you know a particular line in your project is a hotspot, you can pass the (relative) path to its containing file in a `filename` paramater, with the line number in `line`.
