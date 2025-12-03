import sys

from rich import print


def setup_prereqs():
    if sys.platform != "linux":
        print("[bold red]error:[/bold red] Accelerant currently only supports Linux.")
        sys.exit(1)

    with open("/proc/sys/kernel/perf_event_paranoid", "r") as f:
        val = int(f.read().strip())
        if val > 1:
            print(
                "[bold red]error:[/bold red] kernel perf events are restricted (value > 1). "
                "Please run the following command as root to allow access:\n\n"
                "    sudo sh -c 'echo 1 > /proc/sys/kernel/perf_event_paranoid'\n"
            )
            sys.exit(1)
