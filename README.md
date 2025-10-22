# Accelerant

## Setup

1. Git clone
2. Install [`uv`](https://github.com/astral-sh/uv) if not already installed
3. To fix perf debuginfo issues: `cargo install addr2line --features="bin"`

## Basic usage

First, build your target program with optimizations on and debuginfo enabled, and then profile it with `perf` using something like the following:

```console
$ perf record -F99 --call-graph dwarf ./your-program
```

Then, in the `accelerant` repository, run:

```console
$ uv run accelerant_server.py
```

Finally, in a separate terminal, run:

```console
$ curl 'http://127.0.0.1:5000/optimize?project=PATH_TO_PROJECT_ROOT&perfDataPath=ABSOLUTE_PATH_TO_PERF_DATA'
```

Alternatively, you can ask to optimize a specific line without `perf` information using the following:

```console
$ curl 'http://127.0.0.1:5000/optimize?project=PATH_TO_PROJECT_ROOT&filename=RELATIVE_PATH_TO_FILE_IN_PROJECT&line=LINE_NUMBER_IN_FILE'
```
