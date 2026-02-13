import subprocess
from typing import List


class Bash:
    """
    Low-level shell command executor.
    """

    @staticmethod
    def run(cmd: List[str]) -> str:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return result.stdout.strip()


def run_wg_command(cmd: List[str]) -> str:
    """
    Convenience wrapper for running WireGuard-related shell commands.
    """
    return Bash.run(cmd)
