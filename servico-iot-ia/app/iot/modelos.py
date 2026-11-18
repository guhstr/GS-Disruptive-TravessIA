from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class StatusComando(str, Enum):
    PENDENTE = "PENDENTE"
    ACEITO = "ACEITO"
    EXECUTADO = "EXECUTADO"
    REJEITADO = "REJEITADO"
    SEM_CONFIRMACAO = "SEM_CONFIRMACAO"
    FALHA_MQTT = "FALHA_MQTT"
    DISPOSITIVO_OFFLINE = "DISPOSITIVO_OFFLINE"
    DISPOSITIVO_REINICIADO = "DISPOSITIVO_REINICIADO"


STATUS_FINAIS = {
    StatusComando.EXECUTADO,
    StatusComando.REJEITADO,
    StatusComando.SEM_CONFIRMACAO,
    StatusComando.FALHA_MQTT,
    StatusComando.DISPOSITIVO_OFFLINE,
    StatusComando.DISPOSITIVO_REINICIADO,
}


class PedidoExtensao(BaseModel):
    solicitacao_id: int = Field(alias="solicitacaoId", gt=0)
    semaforo_id: int = Field(alias="semaforoId", gt=0)
    segundos_extras: int = Field(alias="segundosExtras", gt=0)
    semaforo_nome: Optional[str] = Field(default=None, alias="semaforoNome", max_length=200)

    model_config = {"populate_by_name": True}


class ResultadoComando(BaseModel):
    request_id: str = Field(serialization_alias="requestId")
    solicitacao_id: int = Field(serialization_alias="solicitacaoId")
    semaforo_id: int = Field(serialization_alias="semaforoId")
    segundos_extras: int = Field(serialization_alias="segundosExtras")
    status: StatusComando
    motivo: Optional[str] = None
    segundos_aplicados: Optional[int] = Field(default=None, serialization_alias="segundosAplicados")
    duracao_ms: Optional[int] = Field(default=None, serialization_alias="duracaoMs")
    # Segundos que faltavam para o sinal de pedestres fechar quando o ESP32 confirmou a execucao.
    travessia_restante_segundos: Optional[int] = Field(default=None,
                                                       serialization_alias="travessiaRestanteSegundos")
