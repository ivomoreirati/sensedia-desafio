"""CLI de provisionamento — comandos `up` e `destroy`.

Camada fina sobre terraform_runner: parseia argumentos, valida entrada
antes de qualquer efeito colateral, e traduz o resultado do Terraform em
algo legível para um operador que nunca viu este código.
"""

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

    typer.echo(f"Inicializando terraform para o ambiente '{env.value}'...")
    try:
        terraform_runner.init(tf_env)
    except terraform_runner.TerraformError as exc:
        typer.echo(f"Erro ao inicializar o terraform:\n{exc.stderr}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Aplicando ambiente '{env.value}'...")
    try:
        result = terraform_runner.apply(env.value, tf_env)
    except terraform_runner.TerraformError as exc:
        typer.echo(f"Erro ao provisionar o ambiente '{env.value}':\n{exc.stderr}", err=True)
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

    try:
        terraform_runner.init(tf_env)
    except terraform_runner.TerraformError as exc:
        typer.echo(f"Erro ao inicializar o terraform:\n{exc.stderr}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Destruindo ambiente '{env.value}'...")
    try:
        result = terraform_runner.destroy(env.value, tf_env)
    except terraform_runner.TerraformError as exc:
        typer.echo(f"Erro ao destruir o ambiente '{env.value}':\n{exc.stderr}", err=True)
        raise typer.Exit(code=1)

    if "No objects need to be destroyed" in result:
        typer.echo(f"Ambiente '{env.value}' já estava destruído — nada a fazer.")
    else:
        typer.echo(f"Ambiente '{env.value}' destruído com sucesso.")


if __name__ == "__main__":
    app()
