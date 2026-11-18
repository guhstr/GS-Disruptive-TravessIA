from dataclasses import asdict
from typing import List, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.faq.assistente import MensagemHistorico
from app.ia.cliente_gemini import IaIndisponivelError

router = APIRouter(prefix="/api/faq", tags=["Assistente de duvidas (RAG)"])


class Mensagem(BaseModel):
    papel: Literal["usuario", "assistente"]
    texto: str = Field(min_length=1, max_length=2000)


class Pergunta(BaseModel):
    pergunta: str = Field(min_length=3, max_length=500)
    historico: List[Mensagem] = Field(default_factory=list, max_length=10)
    simplificar: bool = False


class PedidoOrientacao(BaseModel):
    condicao_climatica: str = Field(alias="condicaoClimatica", min_length=1, max_length=100)
    segundos_extras: int = Field(alias="segundosExtras", ge=1, le=15)
    periodo: Literal["dia", "noite"] = "dia"


def _camel(dados: dict) -> dict:
    return {
        "resposta": dados["resposta"],
        "contextoSuficiente": dados["contexto_suficiente"],
        "fontes": dados["fontes"],
        "modelo": dados["modelo"],
        "maiorSimilaridade": dados["maior_similaridade"],
        "perguntaConsiderada": dados["pergunta_considerada"],
        "sugestoes": dados["sugestoes"],
        "motivoRecusa": dados["motivo_recusa"],
    }


@router.post("/perguntas")
def perguntar(corpo: Pergunta, request: Request) -> dict:
    """Responde a pergunta usando apenas a base de conhecimento, considerando as mensagens anteriores."""
    historico = [MensagemHistorico(m.papel, m.texto) for m in corpo.historico]
    try:
        resposta = request.app.state.assistente.responder(corpo.pergunta.strip(), historico, corpo.simplificar)
    except IaIndisponivelError as erro:
        raise HTTPException(status_code=503, detail=f"Assistente indisponivel no momento: {erro}")
    return _camel(asdict(resposta))


@router.post("/orientacao")
def orientar(corpo: PedidoOrientacao, request: Request) -> dict:
    """Orientacao para quem vai atravessar, com dicas da base para o clima e o periodo do dia.
    Nunca falha: sem IA, devolve uma mensagem padrao."""
    orientacao = request.app.state.assistente.orientar(
        corpo.condicao_climatica.strip(), corpo.segundos_extras, corpo.periodo)
    return {
        "mensagem": orientacao.mensagem,
        "geradaPorIa": orientacao.gerada_por_ia,
        "fontes": [asdict(f) for f in orientacao.fontes],
        "modelo": orientacao.modelo,
    }
