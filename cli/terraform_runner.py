"""Wrapper fino sobre `terraform`, invocado via subprocess.

Não tem lógica de CLI (mensagens pro operador, exit codes) — isso fica em
main.py. Aqui só existe "rodar terraform e reportar o que aconteceu".
"""

import subprocess
from pathlib import Path

INFRA_DIR = Path(__file__).resolve().parent.parent / "infra"


class TerraformError(Exception):
    """Erro ao rodar um comando terraform. `stderr` traz o motivo real."""

    def __init__(self, command: list[str], stderr: str):
        self.command = command
        self.stderr = stderr
        super().__init__(f"terraform {' '.join(command)} falhou")


def _run(args: list[str], env: dict[str, str]) -> str:
    result = subprocess.run(
        ["terraform", *args],
        cwd=INFRA_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TerraformError(args, result.stderr)
    return result.stdout


def init(env: dict[str, str]) -> None:
    _run(["init", "-input=false"], env)


def apply(env_name: str, env: dict[str, str]) -> str:
    return _run(
        [
            "apply",
            "-auto-approve",
            "-input=false",
            f"-var-file=envs/{env_name}.tfvars",
        ],
        env,
    )


def destroy(env_name: str, env: dict[str, str]) -> str:
    return _run(
        [
            "destroy",
            "-auto-approve",
            "-input=false",
            f"-var-file=envs/{env_name}.tfvars",
        ],
        env,
    )


def output(env: dict[str, str]) -> str:
    return _run(["output", "-json"], env)
