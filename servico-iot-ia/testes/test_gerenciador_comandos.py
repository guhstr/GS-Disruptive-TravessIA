import json
import threading
import time

import pytest

from app.config import Configuracao
from app.iot.gerenciador_comandos import GerenciadorComandos, SemaforoOcupadoError
from app.iot.modelos import PedidoExtensao, StatusComando


def configuracao(aceite=1, execucao=1):
    return Configuracao("localhost", 1883, "teste/travessia", aceite, execucao, 15)


class DispositivoFalso:
    """Responde aos comandos publicados como o ESP32 responderia."""

    def __init__(self, respostas=("ACEITO", "EXECUTADO"), publicacao_ok=True):
        self.respostas = respostas
        self.publicacao_ok = publicacao_ok
        self.publicados = []
        self.gerenciador = None

    def publicar(self, topico, mensagem):
        self.publicados.append((topico, json.loads(mensagem)))
        if not self.publicacao_ok:
            return False
        request_id = json.loads(mensagem)["requestId"]
        semaforo_id = int(topico.split("/")[-2])

        def responder():
            for status in self.respostas:
                time.sleep(0.05)
                self.gerenciador.processar_confirmacao(semaforo_id, json.dumps(
                    {"requestId": request_id, "status": status, "segundosAplicados": 10,
                     "travessiaRestanteMs": 24600 if status == "EXECUTADO" else None,
                     "motivo": "FORA_DO_LIMITE" if status == "REJEITADO" else None}))
        threading.Thread(target=responder, daemon=True).start()
        return True


def criar(dispositivo, **kwargs):
    gerenciador = GerenciadorComandos(configuracao(**kwargs), dispositivo.publicar)
    dispositivo.gerenciador = gerenciador
    return gerenciador


def pedido(solicitacao=1, semaforo=1, segundos=10):
    return PedidoExtensao(solicitacaoId=solicitacao, semaforoId=semaforo, segundosExtras=segundos)


def test_fluxo_completo_retorna_executado_e_publica_no_topico_do_semaforo():
    dispositivo = DispositivoFalso()
    resultado = criar(dispositivo).solicitar_extensao(pedido(semaforo=7))
    assert resultado.status == StatusComando.EXECUTADO
    assert resultado.segundos_aplicados == 10
    assert resultado.travessia_restante_segundos == 25
    topico, mensagem = dispositivo.publicados[0]
    assert topico == "teste/travessia/semaforo/7/comando"
    assert mensagem["acao"] == "ESTENDER_TRAVESSIA" and mensagem["segundosExtras"] == 10


def test_publicar_nao_basta_sem_resposta_o_status_e_sem_confirmacao():
    dispositivo = DispositivoFalso(respostas=())
    resultado = criar(dispositivo).solicitar_extensao(pedido())
    assert resultado.status == StatusComando.SEM_CONFIRMACAO


def test_aceito_sem_execucao_no_prazo_permanece_aceito():
    dispositivo = DispositivoFalso(respostas=("ACEITO",))
    resultado = criar(dispositivo).solicitar_extensao(pedido())
    assert resultado.status == StatusComando.ACEITO


def test_rejeicao_do_dispositivo_e_repassada():
    dispositivo = DispositivoFalso(respostas=("REJEITADO",))
    resultado = criar(dispositivo).solicitar_extensao(pedido())
    assert resultado.status == StatusComando.REJEITADO
    assert resultado.motivo == "FORA_DO_LIMITE"


def test_falha_de_publicacao_gera_falha_mqtt():
    dispositivo = DispositivoFalso(publicacao_ok=False)
    resultado = criar(dispositivo).solicitar_extensao(pedido())
    assert resultado.status == StatusComando.FALHA_MQTT


def test_segundos_acima_do_limite_sao_recusados_antes_de_publicar():
    dispositivo = DispositivoFalso()
    with pytest.raises(ValueError):
        criar(dispositivo).solicitar_extensao(pedido(segundos=60))
    assert dispositivo.publicados == []


def test_solicitacao_duplicada_reaproveita_o_mesmo_comando():
    dispositivo = DispositivoFalso()
    gerenciador = criar(dispositivo)
    primeiro = gerenciador.solicitar_extensao(pedido(solicitacao=5))
    segundo = gerenciador.solicitar_extensao(pedido(solicitacao=5))
    assert primeiro.request_id == segundo.request_id
    assert len(dispositivo.publicados) == 1


def test_solicitacoes_simultaneas_no_mesmo_semaforo_sao_bloqueadas():
    dispositivo = DispositivoFalso(respostas=())
    gerenciador = criar(dispositivo)
    thread = threading.Thread(target=gerenciador.solicitar_extensao, args=(pedido(solicitacao=1),))
    thread.start()
    time.sleep(0.1)
    with pytest.raises(SemaforoOcupadoError):
        gerenciador.solicitar_extensao(pedido(solicitacao=2))
    thread.join()
    assert len(dispositivo.publicados) == 1


def test_dispositivo_offline_nao_recebe_comando():
    dispositivo = DispositivoFalso()
    gerenciador = criar(dispositivo)
    gerenciador.processar_estado(json.dumps({"online": False}))
    resultado = gerenciador.solicitar_extensao(pedido())
    assert resultado.status == StatusComando.DISPOSITIVO_OFFLINE
    assert dispositivo.publicados == []


def test_reinicio_do_dispositivo_invalida_comando_pendente():
    dispositivo = DispositivoFalso(respostas=("ACEITO",))
    gerenciador = criar(dispositivo, execucao=2)
    gerenciador.processar_estado(json.dumps({"online": True, "bootId": "a1"}))

    def reiniciar():
        time.sleep(0.3)
        gerenciador.processar_estado(json.dumps({"online": True, "bootId": "b2"}))
    threading.Thread(target=reiniciar).start()

    resultado = gerenciador.solicitar_extensao(pedido())
    assert resultado.status == StatusComando.DISPOSITIVO_REINICIADO


def test_confirmacao_invalida_ou_desconhecida_e_ignorada():
    gerenciador = criar(DispositivoFalso())
    gerenciador.processar_confirmacao(1, "isto nao e json")
    gerenciador.processar_confirmacao(1, json.dumps({"requestId": "inexistente", "status": "EXECUTADO"}))


def test_nome_do_semaforo_vai_no_comando_sem_acentos():
    dispositivo = DispositivoFalso()
    gerenciador = criar(dispositivo)
    gerenciador.solicitar_extensao(PedidoExtensao(solicitacaoId=9, semaforoId=25, segundosExtras=5,
                                                  semaforoNome="Av. São João  x  Ipiranga"))
    topico, mensagem = dispositivo.publicados[0]
    assert topico == "teste/travessia/semaforo/25/comando"
    assert mensagem["semaforoNome"] == "Av. Sao Joao x Ipiranga"


def test_estado_da_travessia_segue_o_relogio_do_dispositivo():
    gerenciador = criar(DispositivoFalso())
    assert gerenciador.estado_travessia()["online"] is False
    gerenciador.processar_estado(json.dumps({"online": True, "bootId": "a1", "fase": "PEDESTRE_VERDE",
                                             "semaforoAtual": 25, "travessiaRestanteMs": 12300}))
    estado = gerenciador.estado_travessia()
    assert estado["pedestreAberto"] and estado["travessiaRestanteSegundos"] == 13
    assert estado["semaforoAtual"] == 25
    gerenciador.processar_estado(json.dumps({"online": True, "bootId": "a1", "fase": "TODOS_VERMELHO",
                                             "travessiaRestanteMs": 0, "aberturaPedestreMs": 16200}))
    estado = gerenciador.estado_travessia()
    assert estado["pedestreAberto"] is False
    assert estado["segundosAteAbrir"] == 17


def test_aviso_de_offline_de_execucao_antiga_e_ignorado():
    gerenciador = criar(DispositivoFalso())
    gerenciador.processar_estado(json.dumps({"online": True, "bootId": "novo", "fase": "VEICULOS_VERDE"}))
    gerenciador.processar_estado(json.dumps({"online": False, "bootId": "antigo"}))
    assert gerenciador.dispositivo_online() is True
    gerenciador.processar_estado(json.dumps({"online": False, "bootId": "novo"}))
    assert gerenciador.dispositivo_online() is False
