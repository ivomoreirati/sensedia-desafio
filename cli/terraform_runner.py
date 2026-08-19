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


def select_workspace(env_name: str, env: dict[str, str]) -> None:
    """Garante que dev e stg tenham state isolado (um workspace cada).

    Sem isso, aplicar --env stg depois de --env dev destruiria os recursos
    de dev para criar os de stg — os dois compartilhariam o mesmo state
    local em vez de coexistirem isolados.
    """
    try:
        _run(["workspace", "select", env_name], env)
    except TerraformError:
        _run(["workspace", "new", env_name], env)


def list_workspaces(env: dict[str, str]) -> list[str]:
    output_text = _run(["workspace", "list"], env)
    return [line.strip().lstrip("*").strip() for line in output_text.splitlines() if line.strip()]


def select_existing_workspace(env_name: str, env: dict[str, str]) -> None:
    """Troca pro workspace do ambiente, sem criar um novo se não existir.

    Usado por `status`, que não deve ter nenhum efeito colateral — nem
    criar um workspace vazio para um ambiente nunca provisionado.
    """
    _run(["workspace", "select", env_name], env)


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
