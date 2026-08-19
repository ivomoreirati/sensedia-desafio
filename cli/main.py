"""CLI de provisionamento — comandos `up` e `destroy`.

Camada fina sobre terraform_runner: parseia argumentos, valida entrada
antes de qualquer efeito colateral, e traduz o resultado do Terraform em
algo legível para um operador que nunca viu este código.
"""

import json
import os
import shutil
from enum import Enum

import typer
from dotenv import load_dotenv

from cli import terraform_runner

app = typer.Typer(add_completion=False, no_args_is_help=True)

REQUIRED_ENV_VARS = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]


class Env(str, Enum):
    dev = "dev"
    stg = "stg"


_CONNECTION_HINT = (
    "Isso geralmente significa que o LocalStack não está rodando. "
    "Confira com: docker compose up -d"
)


def _print_terraform_error(action: str, stderr: str) -> None:
    """Erro do Terraform tem duas partes: uma dica prática (quando dá pra
    reconhecer a causa) e o detalhe técnico bruto — nunca só o segundo, que
    sozinho não ajuda um operador que nunca viu Terraform por dentro.
    """
    typer.echo(f"Erro ao {action}.", err=True)
    if "connection refused" in stderr.lower() or "dial tcp" in stderr.lower():
        typer.echo(_CONNECTION_HINT, err=True)
    typer.echo("\nDetalhe técnico (saída do Terraform):", err=True)
    typer.echo(stderr, err=True)


@app.callback()
def check_prereqs():
    load_dotenv()

    if shutil.which("terraform") is None:
        typer.echo(
            "Erro: binário 'terraform' não encontrado no PATH.\n"
            "Instale o Terraform (https://developer.hashicorp.com/terraform/install) "
            "e tente novamente.",
            err=True,
        )
        raise typer.Exit(code=1)


def _init_workspace(env_name: str, tf_env: dict[str, str]) -> None:
    typer.echo(f"Inicializando terraform para o ambiente '{env_name}'...")
    try:
        terraform_runner.init(tf_env)
        terraform_runner.select_workspace(env_name, tf_env)
    except terraform_runner.TerraformError as exc:
        _print_terraform_error(f"inicializar o terraform para o ambiente '{env_name}'", exc.stderr)
        raise typer.Exit(code=1)


def _build_tf_env() -> dict[str, str]:
    missing = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing:
        typer.echo(
            "Erro: variável(is) de ambiente ausente(s): " + ", ".join(missing) + "\n"
            "Copie .env.example para .env e preencha (para LocalStack, os "
            "valores dummy 'test'/'test' já servem).",
            err=True,
        )
        raise typer.Exit(code=1)
    return os.environ.copy()


@app.command()
def up(
    env: Env = typer.Option(..., "--env", help="Ambiente a provisionar ou reconciliar."),
):
    """Provisiona ou reconcilia o ambiente. Rodar duas vezes é seguro."""
    tf_env = _build_tf_env()
    _init_workspace(env.value, tf_env)

    typer.echo(f"Aplicando ambiente '{env.value}'...")
    try:
        result = terraform_runner.apply(env.value, tf_env)
    except terraform_runner.TerraformError as exc:
        _print_terraform_error(f"provisionar o ambiente '{env.value}'", exc.stderr)
        raise typer.Exit(code=1)

    if "No changes." in result:
        typer.echo(f"Ambiente '{env.value}' já estava atualizado — nada a fazer.")
    else:
        typer.echo(f"Ambiente '{env.value}' provisionado com sucesso.")


@app.command()
def destroy(
    env: Env = typer.Option(..., "--env", help="Ambiente a destruir."),
    yes: bool = typer.Option(
        False, "--yes", help="Não pedir confirmação (uso em automação/CI)."
    ),
):
    """Remove tudo que foi criado. Seguro rodar em ambiente já destruído."""
    tf_env = _build_tf_env()

    if not yes:
        typer.confirm(
            f"Isso vai destruir todos os recursos do ambiente '{env.value}'. Confirma?",
            abort=True,
        )

    _init_workspace(env.value, tf_env)

    typer.echo(f"Destruindo ambiente '{env.value}'...")
    try:
        result = terraform_runner.destroy(env.value, tf_env)
    except terraform_runner.TerraformError as exc:
        _print_terraform_error(f"destruir o ambiente '{env.value}'", exc.stderr)
        raise typer.Exit(code=1)

    if "No objects need to be destroyed" in result:
        typer.echo(f"Ambiente '{env.value}' já estava destruído — nada a fazer.")
    else:
        typer.echo(f"Ambiente '{env.value}' destruído com sucesso.")


@app.command()
def status(
    env: Env = typer.Option(..., "--env", help="Ambiente a inspecionar."),
):
    """Mostra se o ambiente está provisionado. Não cria, muda nem destrói nada."""
    tf_env = _build_tf_env()

    try:
        terraform_runner.init(tf_env)
        workspaces = terraform_runner.list_workspaces(tf_env)
    except terraform_runner.TerraformError as exc:
        _print_terraform_error(f"inicializar o terraform para o ambiente '{env.value}'", exc.stderr)
        raise typer.Exit(code=1)

    if env.value not in workspaces:
        typer.echo(f"Ambiente '{env.value}' nunca foi provisionado.")
        return

    try:
        terraform_runner.select_existing_workspace(env.value, tf_env)
        outputs = json.loads(terraform_runner.output(tf_env))
    except terraform_runner.TerraformError as exc:
        _print_terraform_error(f"consultar o ambiente '{env.value}'", exc.stderr)
        raise typer.Exit(code=1)

    if not outputs:
        typer.echo(f"Ambiente '{env.value}' está destruído — sem recursos ativos.")
        return

    typer.echo(f"Ambiente '{env.value}' está provisionado:")
    for key, data in outputs.items():
        typer.echo(f"  {key}: {data['value']}")


if __name__ == "__main__":
    app()
