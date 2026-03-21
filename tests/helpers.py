"""Shared pytest helpers available to all test modules."""

from services.executor import CommandResult


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(return_code=0, stdout=stdout, stderr="")


def _fail(stderr: str = "PowerShell error") -> CommandResult:
    return CommandResult(return_code=1, stdout="", stderr=stderr)


def _unavailable() -> CommandResult:
    return CommandResult(return_code=-2, stdout="", stderr="powershell.exe not found")
