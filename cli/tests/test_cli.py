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


@pytest.fixture(autouse=True)
def fake_workspace_selection(monkeypatch):
    """Por padrão, simula que dev/stg já existem e toda operação de
    workspace funciona sem tocar terraform de verdade.

    Testes que precisam verificar o comportamento de init/workspace
    especificamente sobrescrevem isso.
    """
    monkeypatch.setattr(cli_main.terraform_runner, "init", lambda env: None)
    monkeypatch.setattr(cli_main.terraform_runner, "select_workspace", lambda env_name, env: None)
    monkeypatch.setattr(cli_main.terraform_runner, "list_workspaces", lambda env: ["default", "dev", "stg"])
    monkeypatch.setattr(cli_main.terraform_runner, "select_existing_workspace", lambda env_name, env: None)


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
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "apply",
            lambda env_name, env: "No changes. Your infrastructure matches the configuration.",
        )

        result = runner.invoke(cli_main.app, ["up", "--env", "dev"])

        assert result.exit_code == 0
        assert "já estava atualizado" in result.output

    def test_reporta_sucesso_quando_terraform_aplica_mudancas(self, monkeypatch):
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "apply",
            lambda env_name, env: "Apply complete! Resources: 5 added, 0 changed, 0 destroyed.",
        )

        result = runner.invoke(cli_main.app, ["up", "--env", "dev"])

        assert result.exit_code == 0
        assert "provisionado com sucesso" in result.output

    def test_traduz_erro_do_terraform_sem_expor_stacktrace_python(self, monkeypatch):
        def _falha(env_name, env):
            raise TerraformError(["apply"], "mensagem de erro real do terraform")

        monkeypatch.setattr(cli_main.terraform_runner, "apply", _falha)

        result = runner.invoke(cli_main.app, ["up", "--env", "dev"])

        assert result.exit_code == 1
        assert "mensagem de erro real do terraform" in result.output
        assert "Traceback" not in result.output

    def test_erro_de_conexao_sugere_subir_o_localstack(self, monkeypatch):
        def _falha(env_name, env):
            raise TerraformError(["apply"], "dial tcp 127.0.0.1:4566: connect: connection refused")

        monkeypatch.setattr(cli_main.terraform_runner, "apply", _falha)

        result = runner.invoke(cli_main.app, ["up", "--env", "dev"])

        assert result.exit_code == 1
        assert "docker compose up" in result.output

    def test_seleciona_workspace_isolado_por_ambiente(self, monkeypatch):
        """dev e stg precisam de state separado — ver terraform_runner.select_workspace."""
        selected = []
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "select_workspace",
            lambda env_name, env: selected.append(env_name),
        )
        monkeypatch.setattr(cli_main.terraform_runner, "apply", lambda env_name, env: "Apply complete!")

        runner.invoke(cli_main.app, ["up", "--env", "stg"])

        assert selected == ["stg"]


class TestComandoDestroy:
    def test_pede_confirmacao_por_padrao_e_aborta_se_recusado(self, monkeypatch):
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
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "destroy",
            lambda env_name, env: "Destroy complete! Resources: 5 destroyed.",
        )

        result = runner.invoke(cli_main.app, ["destroy", "--env", "dev", "--yes"])

        assert result.exit_code == 0
        assert "destruído com sucesso" in result.output

    def test_reporta_nada_a_fazer_em_ambiente_ja_destruido(self, monkeypatch):
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "destroy",
            lambda env_name, env: "No changes. No objects need to be destroyed.",
        )

        result = runner.invoke(cli_main.app, ["destroy", "--env", "dev", "--yes"])

        assert result.exit_code == 0
        assert "já estava destruído" in result.output

    def test_ambiente_nunca_provisionado_nao_cria_workspace(self, monkeypatch):
        """Bug real encontrado em revisão de qualidade: destroy usava
        select-or-create, então rodar destroy num ambiente nunca provisionado
        criava um workspace vazio como efeito colateral — depois disso,
        status passava a reportar "destruído" em vez de "nunca provisionado"
        pro mesmo ambiente. Confirmado ao vivo contra o LocalStack antes da
        correção."""
        monkeypatch.setattr(cli_main.terraform_runner, "list_workspaces", lambda env: ["default"])
        select_called = []
        destroy_called = []
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "select_existing_workspace",
            lambda env_name, env: select_called.append(env_name),
        )
        monkeypatch.setattr(
            cli_main.terraform_runner, "destroy", lambda env_name, env: destroy_called.append(env_name)
        )

        result = runner.invoke(cli_main.app, ["destroy", "--env", "dev", "--yes"])

        assert result.exit_code == 0
        assert "nunca foi provisionado" in result.output
        assert select_called == []
        assert destroy_called == []


class TestComandoStatus:
    def test_ambiente_nunca_provisionado(self, monkeypatch):
        monkeypatch.setattr(cli_main.terraform_runner, "list_workspaces", lambda env: ["default"])

        result = runner.invoke(cli_main.app, ["status", "--env", "dev"])

        assert result.exit_code == 0
        assert "nunca foi provisionado" in result.output

    def test_ambiente_provisionado_mostra_outputs(self, monkeypatch):
        monkeypatch.setattr(cli_main.terraform_runner, "list_workspaces", lambda env: ["default", "dev"])
        monkeypatch.setattr(cli_main.terraform_runner, "select_existing_workspace", lambda env_name, env: None)
        monkeypatch.setattr(
            cli_main.terraform_runner,
            "output",
            lambda env: '{"function_url": {"value": "http://example.com"}, "table_name": {"value": "products-dev"}}',
        )

        result = runner.invoke(cli_main.app, ["status", "--env", "dev"])

        assert result.exit_code == 0
        assert "está provisionado" in result.output
        assert "http://example.com" in result.output
        assert "products-dev" in result.output

    def test_output_json_malformado_falha_sem_expor_stacktrace_python(self, monkeypatch):
        """Achado em revisão de qualidade: json.loads sem try/except deixava
        um JSONDecodeError vazar como traceback cru se `terraform output
        -json` retornasse algo inesperado — violando o princípio de nunca
        expor stacktrace Python ao operador."""
        monkeypatch.setattr(cli_main.terraform_runner, "output", lambda env: "isso não é json")

        result = runner.invoke(cli_main.app, ["status", "--env", "dev"])

        assert result.exit_code == 1
        assert "Traceback" not in result.output

    def test_ambiente_destruido_sem_recursos(self, monkeypatch):
        monkeypatch.setattr(cli_main.terraform_runner, "list_workspaces", lambda env: ["default", "dev"])
        monkeypatch.setattr(cli_main.terraform_runner, "select_existing_workspace", lambda env_name, env: None)
        monkeypatch.setattr(cli_main.terraform_runner, "output", lambda env: "{}")

        result = runner.invoke(cli_main.app, ["status", "--env", "dev"])

        assert result.exit_code == 0
        assert "sem recursos ativos" in result.output

    def test_nao_chama_apply_nem_destroy(self, monkeypatch):
        """status nunca deve ter efeito colateral no ambiente."""
        called = []
        monkeypatch.setattr(cli_main.terraform_runner, "list_workspaces", lambda env: ["default", "dev"])
        monkeypatch.setattr(cli_main.terraform_runner, "select_existing_workspace", lambda env_name, env: None)
        monkeypatch.setattr(cli_main.terraform_runner, "output", lambda env: "{}")
        monkeypatch.setattr(cli_main.terraform_runner, "apply", lambda *a: called.append("apply"))
        monkeypatch.setattr(cli_main.terraform_runner, "destroy", lambda *a: called.append("destroy"))

        runner.invoke(cli_main.app, ["status", "--env", "dev"])

        assert called == []
