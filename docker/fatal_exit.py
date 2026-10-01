#!/usr/bin/env python3
"""Supervisor event listener: stop supervisord when a program goes FATAL (audit I1-2).

supervisord is PID 1 in the Speedarr image. When the backend fails to start three times it goes
FATAL and supervisord stops trying but keeps running, so the container stays Up and Docker's
restart policy never fires. This listener subscribes to PROCESS_STATE_FATAL and sends supervisord,
its parent, SIGTERM: supervisord shuts down, the container exits, and `restart: unless-stopped`
(or `always`) starts it again. Stdout is the listener protocol channel and carries nothing else;
everything human-readable goes to stderr. Stdlib only.
"""
import os
import signal
import sys


def _fields(text):
    return dict(part.split(":", 1) for part in text.split())


def handle(header, payload, kill=lambda: os.kill(os.getppid(), signal.SIGTERM)):
    """Act on one event; returns True when supervisord was told to stop."""
    if _fields(header).get("eventname") != "PROCESS_STATE_FATAL":
        return False
    name = _fields(payload).get("processname", "?")
    sys.stderr.write(f"fatal-exit: {name} is FATAL; stopping supervisord so the container exits\n")
    sys.stderr.flush()
    kill()
    return True


def main():
    while True:
        sys.stdout.write("READY\n")
        sys.stdout.flush()
        header = sys.stdin.readline()
        if not header:
            return
        payload = sys.stdin.read(int(_fields(header).get("len", 0)))
        handle(header, payload)
        sys.stdout.write("RESULT 2\nOK")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
