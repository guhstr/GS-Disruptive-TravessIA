import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import RAIZ_REPOSITORIO, carregar_configuracao
from app.faq.assistente import AssistenteFaq
from app.faq.rotas import router as rotas_faq
from app.ia.cliente_gemini import ClienteGemini, IaIndisponivelError
from app.iot.cliente_mqtt import ClienteMqtt
from app.iot.rotas import router as rotas_iot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    cliente = ClienteMqtt(carregar_configuracao())
    cliente.iniciar()
    app.state.mqtt = cliente

    assistente = AssistenteFaq(
        ClienteGemini(),
        pasta_base=RAIZ_REPOSITORIO / "base-conhecimento",
        arquivo_indice=RAIZ_REPOSITORIO / "servico-iot-ia" / "dados" / "indice_rag.json",
        limiar_similaridade=float(os.getenv("RAG_LIMIAR_SIMILARIDADE", "0.62")),
        quantidade_trechos=int(os.getenv("RAG_QUANTIDADE_TRECHOS", "4")),
        modo_busca=os.getenv("RAG_MODO_BUSCA", "vetorial"),
    )
    try:
        assistente.preparar()
    except IaIndisponivelError as erro:
        logging.getLogger(__name__).warning("Indice RAG nao preparado na inicializacao: %s", erro)
    app.state.assistente = assistente
    yield
    cliente.parar()


app = FastAPI(title="Travessia Inteligente - Servico IoT e IA", lifespan=ciclo_de_vida)
app.include_router(rotas_iot)
app.include_router(rotas_faq)
