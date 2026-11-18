import logging
import threading
import uuid

import paho.mqtt.client as mqtt

from app.config import Configuracao
from app.iot.gerenciador_comandos import GerenciadorComandos

log = logging.getLogger(__name__)

QOS = 1


class ClienteMqtt:
    """Conexao com o broker: publica comandos e encaminha respostas ao gerenciador."""

    def __init__(self, configuracao: Configuracao):
        self._config = configuracao
        self._conectado = threading.Event()
        self._cliente = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"travessia-servico-{uuid.uuid4().hex[:8]}",
        )
        self._cliente.on_connect = self._ao_conectar
        self._cliente.on_disconnect = self._ao_desconectar
        self._cliente.on_message = self._ao_receber
        self._cliente.reconnect_delay_set(min_delay=1, max_delay=10)
        self.gerenciador = GerenciadorComandos(configuracao, self.publicar)

    @property
    def conectado(self) -> bool:
        return self._conectado.is_set()

    def iniciar(self) -> None:
        log.info("Conectando ao broker %s:%s", self._config.mqtt_host, self._config.mqtt_porta)
        self._cliente.connect_async(self._config.mqtt_host, self._config.mqtt_porta, keepalive=30)
        self._cliente.loop_start()
        if not self._conectado.wait(10):
            log.warning("Broker MQTT ainda indisponivel; novas tentativas em segundo plano")

    def parar(self) -> None:
        self._cliente.loop_stop()
        self._cliente.disconnect()

    def publicar(self, topico: str, mensagem: str) -> bool:
        if not self.conectado:
            log.error("Publicacao cancelada: sem conexao com o broker")
            return False
        info = self._cliente.publish(topico, mensagem, qos=QOS)
        try:
            info.wait_for_publish(timeout=5)
        except (RuntimeError, ValueError) as erro:
            log.error("Falha ao publicar em %s: %s", topico, erro)
            return False
        if not info.is_published():
            log.error("Broker nao confirmou a publicacao em %s", topico)
            return False
        log.info("Publicado em %s: %s", topico, mensagem)
        return True

    def _ao_conectar(self, cliente, _userdata, _flags, codigo, _props):
        if codigo.is_failure:
            log.error("Conexao MQTT recusada: %s", codigo)
            return
        base = self._config.mqtt_topico_base
        cliente.subscribe([(f"{base}/semaforo/+/confirmacao", QOS),
                           (self.gerenciador.topico_estado_dispositivo, QOS)])
        self._conectado.set()
        log.info("Conectado ao broker MQTT e inscrito em %s/semaforo/+/confirmacao e %s/dispositivo/estado", base, base)

    def _ao_desconectar(self, _cliente, _userdata, _flags, codigo, _props):
        self._conectado.clear()
        log.warning("Desconectado do broker MQTT (%s)", codigo)

    def _ao_receber(self, _cliente, _userdata, mensagem):
        payload = mensagem.payload.decode("utf-8", errors="replace")
        if mensagem.topic == self.gerenciador.topico_estado_dispositivo:
            log.debug("Estado do dispositivo: %s", payload)
            self.gerenciador.processar_estado(payload)
            return
        partes = mensagem.topic.split("/")
        try:
            semaforo_id = int(partes[-2])
        except (IndexError, ValueError):
            log.warning("Topico fora do padrao: %s", mensagem.topic)
            return
        log.info("Recebido em %s: %s", mensagem.topic, payload)
        if partes[-1] == "confirmacao":
            self.gerenciador.processar_confirmacao(semaforo_id, payload)
