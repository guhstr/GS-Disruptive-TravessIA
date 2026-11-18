from fastapi import APIRouter, HTTPException, Request

from app.iot.gerenciador_comandos import SemaforoOcupadoError
from app.iot.modelos import PedidoExtensao, ResultadoComando

router = APIRouter(prefix="/api/iot", tags=["IoT - Semaforo"])


def _gerenciador(request: Request):
    return request.app.state.mqtt.gerenciador


@router.post("/extensoes", response_model=ResultadoComando, response_model_by_alias=True)
def solicitar_extensao(pedido: PedidoExtensao, request: Request) -> ResultadoComando:
    """Publica o comando para o ESP32 e aguarda a confirmacao do dispositivo."""
    try:
        return _gerenciador(request).solicitar_extensao(pedido)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro))
    except SemaforoOcupadoError as erro:
        raise HTTPException(status_code=409, detail=str(erro))


@router.get("/dispositivo")
def estado_dispositivo(request: Request) -> dict:
    """Fase atual do semaforo simulado e quanto falta para o sinal de pedestres fechar."""
    return _gerenciador(request).estado_travessia()


@router.get("/status")
def status_conexao(request: Request) -> dict:
    return {"brokerConectado": request.app.state.mqtt.conectado}
