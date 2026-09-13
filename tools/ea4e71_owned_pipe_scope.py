"""Test-owned stdin descriptor rule, not a general descriptor exemption."""

from contextlib import contextmanager
import os
import subprocess
import threading


class OwnedPipeScope:
    def __init__(self, constructor_code):
        self.constructor_code = constructor_code
        self.local = threading.local()

    @contextmanager
    def creation(self, command):
        if getattr(self.local, "command", None) is not None:
            raise RuntimeError("nested pipe creation scope prohibited")
        self.local.command = list(command)
        try:
            yield
        finally:
            self.local.command = None

    def allows(self, event, args, caller):
        command = getattr(self.local, "command", None)
        if command is None or event != "open" or len(args) != 3 or caller is None:
            return False
        descriptor, mode, flags = args
        if type(descriptor) is not int or descriptor < 0 or mode not in {"w", "wb"}:
            return False
        if type(flags) is not int or flags & (os.O_WRONLY | os.O_RDWR) != os.O_WRONLY:
            return False
        if caller.f_code is not self.constructor_code:
            return False
        values = caller.f_locals
        child = values.get("self")
        return (type(values.get("p2cwrite")) is int and values["p2cwrite"] == descriptor
                and values.get("stdin") == subprocess.PIPE
                and child is not None and getattr(child, "args", None) == command)
