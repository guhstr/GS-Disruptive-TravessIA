import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ_REPOSITORIO / ".env")


def _inteiro(nome: str, padrao: int) -> int:
    valor = os.getenv(nome, "").strip()
    return int(valor) if valor else padrao


@dataclass(frozen=True)
class Configuracao:
    mqtt_host: str
    mqtt_porta: int
    mqtt_topico_base: str
    timeout_aceite_segundos: int
    timeout_execucao_segundos: int
    segundos_extras_maximo: int


def carregar_configuracao() -> Configuracao:
    url = os.getenv("MQTT_BROKER_URL", "tcp://broker.hivemq.com:1883")
    host_porta = url.split("://", 1)[-1]
    host, _, porta = host_porta.partition(":")
    return Configuracao(
        mqtt_host=host,
        mqtt_porta=int(porta or 1883),
        mqtt_topico_base=os.getenv("MQTT_TOPICO_BASE", "fiap/gs2026/travessia").rstrip("/"),
        timeout_aceite_segundos=_inteiro("MQTT_TIMEOUT_CONFIRMACAO_SEGUNDOS", 10),
        timeout_execucao_segundos=_inteiro("MQTT_TIMEOUT_EXECUCAO_SEGUNDOS", 40),
        segundos_extras_maximo=_inteiro("SEGUNDOS_EXTRAS_MAXIMO", 15),
    )
