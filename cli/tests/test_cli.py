"""Testes da CLI que não tocam Docker/LocalStack/rede.

terraform_runner é mockado em todo teste — o que é validado aqui é o
comportamento da própria CLI: parsing, validação, mensagens e exit codes.
O comportamento real do Terraform contra o LocalStack é validado
manualmente (ver ADR-001 e docs/decisions/), não neste arquivo.
"""

import pytest
from typer.testing import CliRunner

from cli import main as cli_main
from cli.terraform_runner import TerraformError

runner = CliRunner()


@pytest.fixture(autouse=True)
def no_dotenv_loading(monkeypatch):
    """Isola os testes de qualquer .env real no disco de quem estiver rodando."""
    monkeypatch.setattr(cli_main, "load_dotenv", lambda: None)


@pytest.fixture(autouse=True)
def fake_terraform_binary(monkeypatch):
    """Por padrão, simula que o binário terraform está disponível."""
    monkeypatch.setattr(cli_main.shutil, "which", lambda name: "/usr/bin/terraform")


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    """Por padrão, simula que as credenciais dummy do LocalStack estão setadas."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")


class TestValidacaoAntesDeQualquerEfeitoColateral:
    def test_up_sem_env_falha_sem_chamar_terraform(self, monkeypatch):
        called = []
        monkeypatch.setattr(cli_main.terraform_runner, "init", lambda env: called.append("init"))

        result = runner.invoke(cli_main.app, ["up"])

        assert result.exit_code == 2
        assert called == []

    def test_up_com_env_invalido_falha_sem_chamar_terraform(self, monkeypatch):
        called = []
        monkeypatch.setattr(cli_main.terraform_runner, "init", lambda env: called.append("init"))

        result = runner.invoke(cli_main.app, ["up", "--env", "producao"])

        assert result.exit_code == 2
        assert called == []

    def test_up_sem_terraform_no_path_falha_com_mensagem_clara(self, monkeypatch):
        monkeypatch.setattr(cli_main.shutil, "which", lambda name: None)

        result = runner.invoke(cli_main.app, ["up", "--env", "dev"])

        assert result.exit_code == 1
        assert "terraform" in result.output.lower()

    def test_up_sem_credenciais_falha_com_mensagem_clara(self, monkeypatch):
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)

        result = runner.invoke(cli_main.app, ["up", "--env", "dev"])

        assert result.exit_code == 1
        assert "AWS_ACCESS_KEY_ID" in result.output


class TestComandoUp:
    def test_reporta_nada_a_fazer_quando_terraform_nao_muda_nada(self, monkeypatch):
        monkeypatch.setattr(cli_main.terraform_runner, "init", lambda env: None)
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "apply",
            lambda env_name, env: "No changes. Your infrastructure matches the configuration.",
        )

        result = runner.invoke(cli_main.app, ["up", "--env", "dev"])

        assert result.exit_code == 0
        assert "já estava atualizado" in result.output

    def test_reporta_sucesso_quando_terraform_aplica_mudancas(self, monkeypatch):
        monkeypatch.setattr(cli_main.terraform_runner, "init", lambda env: None)
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "apply",
            lambda env_name, env: "Apply complete! Resources: 5 added, 0 changed, 0 destroyed.",
        )

        result = runner.invoke(cli_main.app, ["up", "--env", "dev"])

        assert result.exit_code == 0
        assert "provisionado com sucesso" in result.output

    def test_traduz_erro_do_terraform_sem_expor_stacktrace_python(self, monkeypatch):
        monkeypatch.setattr(cli_main.terraform_runner, "init", lambda env: None)

        def _falha(env_name, env):
            raise TerraformError(["apply"], "mensagem de erro real do terraform")

        monkeypatch.setattr(cli_main.terraform_runner, "apply", _falha)

        result = runner.invoke(cli_main.app, ["up", "--env", "dev"])

        assert result.exit_code == 1
        assert "mensagem de erro real do terraform" in result.output
        assert "Traceback" not in result.output


class TestComandoDestroy:
    def test_pede_confirmacao_por_padrao_e_aborta_se_recusado(self, monkeypatch):
        monkeypatch.setattr(cli_main.terraform_runner, "init", lambda env: None)
        destroy_called = []
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "destroy",
            lambda env_name, env: destroy_called.append(env_name),
        )

        result = runner.invoke(cli_main.app, ["destroy", "--env", "dev"], input="n\n")

        assert result.exit_code != 0
        assert destroy_called == []

    def test_yes_pula_confirmacao(self, monkeypatch):
        monkeypatch.setattr(cli_main.terraform_runner, "init", lambda env: None)
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "destroy",
            lambda env_name, env: "Destroy complete! Resources: 5 destroyed.",
        )

        result = runner.invoke(cli_main.app, ["destroy", "--env", "dev", "--yes"])

        assert result.exit_code == 0
        assert "destruído com sucesso" in result.output

    def test_reporta_nada_a_fazer_em_ambiente_ja_destruido(self, monkeypatch):
        monkeypatch.setattr(cli_main.terraform_runner, "init", lambda env: None)
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "destroy",
            lambda env_name, env: "No changes. No objects need to be destroyed.",
        )

        result = runner.invoke(cli_main.app, ["destroy", "--env", "dev", "--yes"])

        assert result.exit_code == 0
        assert "já estava destruído" in result.output
