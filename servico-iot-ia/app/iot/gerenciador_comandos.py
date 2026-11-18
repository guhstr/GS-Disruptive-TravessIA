"""Controle do ciclo de vida dos comandos de extensao enviados ao ESP32.

O gerenciador nao conhece a biblioteca MQTT: recebe uma funcao de publicacao
e e alimentado pelas mensagens de confirmacao e de estado do dispositivo.
Isso permite testar toda a logica sem broker.
"""

import json
import logging
import threading
import unicodedata
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from app.config import Configuracao
from app.iot.modelos import STATUS_FINAIS, PedidoExtensao, ResultadoComando, StatusComando

log = logging.getLogger(__name__)

Publicador = Callable[[str, str], bool]


class SemaforoOcupadoError(Exception):
    """Ja existe um comando aguardando resposta para o mesmo semaforo."""


@dataclass
class _Comando:
    resultado: ResultadoComando
    criado_em: float = field(default_factory=time.monotonic)
    aceite: threading.Event = field(default_factory=threading.Event)
    finalizado: threading.Event = field(default_factory=threading.Event)


@dataclass
class _EstadoDispositivo:
    online: bool
    boot_id: Optional[str]
    fase: Optional[str] = None
    semaforo_atual: Optional[int] = None
    travessia_restante_ms: int = 0
    abertura_pedestre_ms: Optional[int] = None


class GerenciadorComandos:
    def __init__(self, configuracao: Configuracao, publicador: Publicador):
        self._config = configuracao
        self._publicar = publicador
        self._lock = threading.Lock()
        self._comandos: Dict[str, _Comando] = {}
        self._por_solicitacao: Dict[int, str] = {}
        self._semaforo_ocupado: Dict[int, str] = {}
        self._dispositivo: Optional[_EstadoDispositivo] = None
        self._nomes: Dict[str, str] = {}

    def topico(self, semaforo_id: int, tipo: str) -> str:
        return f"{self._config.mqtt_topico_base}/semaforo/{semaforo_id}/{tipo}"

    @property
    def topico_estado_dispositivo(self) -> str:
        return f"{self._config.mqtt_topico_base}/dispositivo/estado"

    def solicitar_extensao(self, pedido: PedidoExtensao) -> ResultadoComando:
        if pedido.segundos_extras > self._config.segundos_extras_maximo:
            raise ValueError(
                f"segundosExtras deve estar entre 1 e {self._config.segundos_extras_maximo}"
            )

        with self._lock:
            existente = self._por_solicitacao.get(pedido.solicitacao_id)
            if existente:
                comando = self._comandos[existente]
                log.info("Solicitacao %s repetida; reaproveitando comando %s",
                         pedido.solicitacao_id, existente)
            else:
                if pedido.semaforo_id in self._semaforo_ocupado:
                    raise SemaforoOcupadoError(
                        f"Ja existe um comando em andamento para o semaforo {pedido.semaforo_id}"
                    )
                comando = self._registrar(pedido)

        if existente:
            comando.finalizado.wait(self._config.timeout_aceite_segundos
                                    + self._config.timeout_execucao_segundos)
            return comando.resultado

        try:
            return self._executar(comando)
        finally:
            with self._lock:
                self._semaforo_ocupado.pop(pedido.semaforo_id, None)

    def processar_confirmacao(self, semaforo_id: int, payload: str) -> None:
        dados = self._ler_json(payload)
        if dados is None:
            return
        comando = self._comandos.get(str(dados.get("requestId", "")))
        if comando is None or comando.resultado.semaforo_id != semaforo_id:
            log.warning("Confirmacao ignorada (requestId desconhecido): %s", payload)
            return

        status_recebido = str(dados.get("status", "")).upper()
        with self._lock:
            resultado = comando.resultado
            if resultado.status in STATUS_FINAIS:
                return
            if status_recebido == "ACEITO":
                resultado.status = StatusComando.ACEITO
                resultado.motivo = dados.get("execucao")
                comando.aceite.set()
            elif status_recebido == "EXECUTADO":
                resultado.status = StatusComando.EXECUTADO
                resultado.segundos_aplicados = dados.get("segundosAplicados")
                restante_ms = dados.get("travessiaRestanteMs")
                if isinstance(restante_ms, (int, float)) and restante_ms >= 0:
                    resultado.travessia_restante_segundos = round(restante_ms / 1000)
                resultado.motivo = None
                self._finalizar(comando)
            elif status_recebido == "REJEITADO":
                resultado.status = StatusComando.REJEITADO
                resultado.motivo = dados.get("motivo")
                self._finalizar(comando)
            else:
                log.warning("Status de confirmacao desconhecido: %s", status_recebido)

    def processar_estado(self, payload: str) -> None:
        """Estado do controlador simulado (ESP32), que atende todos os semaforos."""
        dados = self._ler_json(payload)
        if dados is None:
            return
        online = bool(dados.get("online", False))
        boot_id = dados.get("bootId")

        with self._lock:
            anterior = self._dispositivo
            if (not online and anterior is not None and anterior.online
                    and boot_id and anterior.boot_id and boot_id != anterior.boot_id):
                # LWT atrasado de uma execucao anterior do ESP32: a execucao atual continua online.
                log.info("Aviso de offline do bootId antigo %s ignorado (atual: %s)", boot_id, anterior.boot_id)
                return
            restante = dados.get("travessiaRestanteMs")
            abertura = dados.get("aberturaPedestreMs")
            self._dispositivo = _EstadoDispositivo(
                online, boot_id, dados.get("fase"), dados.get("semaforoAtual"),
                int(restante) if isinstance(restante, (int, float)) and restante > 0 else 0,
                int(abertura) if isinstance(abertura, (int, float)) and abertura >= 0 else None)
            reiniciou = (anterior is not None and anterior.boot_id
                         and boot_id and anterior.boot_id != boot_id)
            if online and not reiniciou:
                return
            novo_status = (StatusComando.DISPOSITIVO_REINICIADO if reiniciou
                           else StatusComando.DISPOSITIVO_OFFLINE)
            for comando in self._comandos.values():
                resultado = comando.resultado
                if resultado.status not in STATUS_FINAIS:
                    resultado.status = novo_status
                    resultado.motivo = "Comando perdido: dispositivo reiniciou" if reiniciou \
                        else "Dispositivo desconectado do broker"
                    self._finalizar(comando)

    def dispositivo_online(self) -> Optional[bool]:
        return self._dispositivo.online if self._dispositivo else None

    def estado_travessia(self) -> dict:
        """Ultimo estado publicado pelo ESP32, para o app acompanhar a contagem da travessia
        no relogio do dispositivo (o Wokwi pode simular mais devagar que o tempo real)."""
        estado = self._dispositivo
        if estado is None or not estado.online:
            return {"online": False, "fase": None, "semaforoAtual": None, "pedestreAberto": False,
                    "travessiaRestanteSegundos": 0, "segundosAteAbrir": None}
        aberto = estado.fase in ("PEDESTRE_VERDE", "PEDESTRE_PISCANDO")
        return {
            "online": True,
            "fase": estado.fase,
            "semaforoAtual": estado.semaforo_atual,
            "pedestreAberto": aberto,
            "travessiaRestanteSegundos": -(-estado.travessia_restante_ms // 1000) if aberto else 0,
            # Quanto falta para o sinal de pedestres abrir (None com o sinal aberto).
            "segundosAteAbrir": (-(-estado.abertura_pedestre_ms // 1000)
                                 if not aberto and estado.abertura_pedestre_ms is not None else None),
        }

    def _registrar(self, pedido: PedidoExtensao) -> _Comando:
        request_id = str(uuid.uuid4())
        comando = _Comando(ResultadoComando(
            request_id=request_id,
            solicitacao_id=pedido.solicitacao_id,
            semaforo_id=pedido.semaforo_id,
            segundos_extras=pedido.segundos_extras,
            status=StatusComando.PENDENTE,
        ))
        self._comandos[request_id] = comando
        if pedido.semaforo_nome:
            self._nomes[request_id] = self._texto_para_lcd(pedido.semaforo_nome)
        self._por_solicitacao[pedido.solicitacao_id] = request_id
        self._semaforo_ocupado[pedido.semaforo_id] = request_id
        return comando

    def _executar(self, comando: _Comando) -> ResultadoComando:
        resultado = comando.resultado

        if self.dispositivo_online() is False:
            self._encerrar(comando, StatusComando.DISPOSITIVO_OFFLINE,
                           "Dispositivo desconectado do broker")
            return resultado

        conteudo = {
            "requestId": resultado.request_id,
            "acao": "ESTENDER_TRAVESSIA",
            "segundosExtras": resultado.segundos_extras,
        }
        nome = self._nomes.get(resultado.request_id)
        if nome:
            conteudo["semaforoNome"] = nome
        mensagem = json.dumps(conteudo)
        if not self._publicar(self.topico(resultado.semaforo_id, "comando"), mensagem):
            self._encerrar(comando, StatusComando.FALHA_MQTT,
                           "Nao foi possivel publicar o comando no broker MQTT")
            return resultado

        if not comando.aceite.wait(self._config.timeout_aceite_segundos):
            self._encerrar(comando, StatusComando.SEM_CONFIRMACAO,
                           f"Dispositivo nao respondeu em {self._config.timeout_aceite_segundos}s")
            return resultado

        if not comando.finalizado.wait(self._config.timeout_execucao_segundos):
            with self._lock:
                if resultado.status == StatusComando.ACEITO:
                    resultado.motivo = "Aceito pelo dispositivo; execucao ainda nao confirmada"
        self._registrar_duracao(comando)
        return resultado

    def _encerrar(self, comando: _Comando, status: StatusComando, motivo: str) -> None:
        with self._lock:
            if comando.resultado.status in STATUS_FINAIS:
                return
            comando.resultado.status = status
            comando.resultado.motivo = motivo
            self._finalizar(comando)
        self._registrar_duracao(comando)

    @staticmethod
    def _finalizar(comando: _Comando) -> None:
        comando.aceite.set()
        comando.finalizado.set()

    @staticmethod
    def _registrar_duracao(comando: _Comando) -> None:
        comando.resultado.duracao_ms = int((time.monotonic() - comando.criado_em) * 1000)

    @staticmethod
    def _texto_para_lcd(texto: str) -> str:
        """O LCD 16x2 nao exibe acentos: remove-os e limita o tamanho."""
        sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
        return " ".join(sem_acento.split())[:60]

    @staticmethod
    def _ler_json(payload: str) -> Optional[dict]:
        try:
            dados = json.loads(payload)
            return dados if isinstance(dados, dict) else None
        except (json.JSONDecodeError, TypeError):
            log.warning("Payload MQTT invalido descartado: %s", payload)
            return None
