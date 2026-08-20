"""Wrapper fino sobre `terraform`, invocado via subprocess.

Não tem lógica de CLI (mensagens pro operador, exit codes) — isso fica em
main.py. Aqui só existe "rodar terraform e reportar o que aconteceu".
"""

import subprocess
from pathlib import Path

INFRA_DIR = Path(__file__).resolve().parent.parent / "infra"

# Sem isso, um terraform travado (ex.: LocalStack não respondendo, o disco
# cheio que já derrubou o Docker nesta mesma sessão) trava a CLI pra sempre,
# sem nenhum feedback pro operador — achado em revisão de qualidade.
DEFAULT_TIMEOUT_SECONDS = 300


class TerraformError(Exception):
    """Erro ao rodar um comando terraform. `stderr` traz o motivo real."""

    def __init__(self, command: list[str], stderr: str):
        self.command = command
        self.stderr = stderr
        super().__init__(f"terraform {' '.join(command)} falhou")


def _run(args: list[str], env: dict[str, str]) -> str:
    try:
        result = subprocess.run(
            ["terraform", *args],
            cwd=INFRA_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise TerraformError(
            args,
            f"terraform não respondeu em {DEFAULT_TIMEOUT_SECONDS}s — pode estar "
            "travado. Verifique se o Docker/LocalStack está saudável "
            "(docker compose logs localstack) e tente de novo.",
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

    Usa `-or-create` em vez de tentar `select` e cair para `new` em
    qualquer falha: essa primeira versão mascarava outras causas de erro
    (state corrompido, permissão) como se fossem só "workspace não existe".
    `-or-create` é a própria ferramenta resolvendo isso — sem depender de
    inspecionar o texto do erro, que pode mudar entre versões do Terraform.
    """
    _run(["workspace", "select", "-or-create", env_name], env)


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
