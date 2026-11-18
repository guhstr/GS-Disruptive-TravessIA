"""Cliente do Google Gemini com troca automatica de modelo.

Usa o endpoint do Gemini compativel com a API OpenAI. Os modelos sao tentados
na ordem configurada: quando um deles esgota a cota (429), nao existe (404)
ou esta indisponivel (5xx/timeout), o proximo e usado. Erros de credencial
(400 de chave invalida, 401, 403) interrompem as tentativas, pois trocar de
modelo nao resolveria.
"""

import logging
import os
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

import httpx

log = logging.getLogger(__name__)

URL_BASE_PADRAO = "https://generativelanguage.googleapis.com/v1beta/openai"
MODELOS_CHAT_PADRAO = (
    "gemini-3.5-flash-lite,gemini-flash-lite-latest,gemini-3.1-flash-lite,gemini-3.5-flash,"
    "gemini-flash-latest,gemini-3.6-flash,gemini-3.7-flash,gemini-3-flash-preview,"
    "gemini-3.1-flash-lite-preview,gemini-3.8-flash,gemini-pro-latest,gemini-3.1-pro-preview"
)
MODELOS_EMBEDDING_PADRAO = "gemini-embedding-2,gemini-embedding-001,gemini-embedding-2-preview"

STATUS_TROCA_DE_MODELO = {404, 408, 409, 429, 500, 502, 503, 504}


class IaIndisponivelError(Exception):
    """Nenhum modelo configurado conseguiu atender a requisicao."""


@dataclass
class RespostaIa:
    conteudo: str
    modelo: str


@dataclass
class ResultadoEmbedding:
    vetores: List[List[float]]
    modelo: str


TAMANHO_LOTE_EMBEDDING = 20
# Limite por minuto do plano gratuito: no 429 de um lote, espera e tenta o mesmo modelo antes de trocar.
ESPERAS_LIMITE_POR_MINUTO = (15, 30, 45)


def _lista(valor: str) -> List[str]:
    return [m.strip() for m in valor.split(",") if m.strip()]


class ClienteGemini:
    def __init__(self, chave: Optional[str] = None, modelos_chat: Optional[Sequence[str]] = None,
                 modelos_embedding: Optional[Sequence[str]] = None, url_base: Optional[str] = None,
                 transporte: Optional[httpx.BaseTransport] = None, timeout: float = 20.0):
        self.chave = chave if chave is not None else os.getenv("GEMINI_API_KEY", "").strip()
        self.modelos_chat = list(modelos_chat or _lista(os.getenv("GEMINI_MODELOS", MODELOS_CHAT_PADRAO)))
        self.modelos_embedding = list(modelos_embedding or _lista(
            os.getenv("GEMINI_MODELOS_EMBEDDING", MODELOS_EMBEDDING_PADRAO)))
        self._http = httpx.Client(
            base_url=url_base or os.getenv("IA_BASE_URL", URL_BASE_PADRAO),
            headers={"Authorization": f"Bearer {self.chave}"},
            timeout=timeout,
            transport=transporte,
        )

    @property
    def configurado(self) -> bool:
        return bool(self.chave)

    def gerar(self, mensagens: List[dict], temperatura: float = 0.2,
              modelos: Optional[Sequence[str]] = None) -> RespostaIa:
        def chamar(modelo: str) -> RespostaIa:
            resposta = self._http.post("/chat/completions", json={
                "model": modelo, "messages": mensagens, "temperature": temperatura})
            resposta.raise_for_status()
            conteudo = resposta.json()["choices"][0]["message"]["content"] or ""
            return RespostaIa(conteudo.strip(), modelo)
        return self._tentar_modelos(list(modelos or self.modelos_chat), chamar, "geracao")

    def embeddings(self, textos: List[str], modelos: Optional[Sequence[str]] = None) -> ResultadoEmbedding:
        """Gera os vetores de todos os textos com um mesmo modelo (vetores de modelos diferentes
        nao sao comparaveis). Se um modelo falhar, todos os textos sao refeitos no proximo."""
        def chamar(modelo: str) -> ResultadoEmbedding:
            vetores: List[List[float]] = []
            for inicio in range(0, len(textos), TAMANHO_LOTE_EMBEDDING):
                lote = textos[inicio:inicio + TAMANHO_LOTE_EMBEDDING]
                resposta = self._http.post("/embeddings", json={"model": modelo, "input": lote})
                for espera in (ESPERAS_LIMITE_POR_MINUTO if len(textos) > 1 else ()):
                    if resposta.status_code != 429:
                        break
                    log.info("Limite por minuto no modelo %s; nova tentativa em %s s", modelo, espera)
                    time.sleep(espera)
                    resposta = self._http.post("/embeddings", json={"model": modelo, "input": lote})
                resposta.raise_for_status()
                dados = sorted(resposta.json()["data"], key=lambda item: item.get("index", 0))
                vetores.extend(item["embedding"] for item in dados)
            return ResultadoEmbedding(vetores, modelo)
        return self._tentar_modelos(list(modelos or self.modelos_embedding), chamar, "embedding")

    def _tentar_modelos(self, modelos: List[str], chamar, finalidade: str):
        if not self.configurado:
            raise IaIndisponivelError("GEMINI_API_KEY nao configurada")
        falhas = []
        for modelo in modelos:
            try:
                resultado = chamar(modelo)
                log.info("IA (%s) atendida pelo modelo %s", finalidade, modelo)
                return resultado
            except httpx.HTTPStatusError as erro:
                status = erro.response.status_code
                corpo = erro.response.text[:200]
                if status in (401, 403) or (status == 400 and "api key" in corpo.lower()):
                    raise IaIndisponivelError(f"Chave do Gemini recusada (HTTP {status})") from erro
                if status not in STATUS_TROCA_DE_MODELO:
                    raise IaIndisponivelError(f"Requisicao recusada pelo Gemini (HTTP {status}): {corpo}") from erro
                falhas.append(f"{modelo}: HTTP {status}")
                log.warning("Modelo %s indisponivel (HTTP %s); tentando o proximo", modelo, status)
            except (httpx.TimeoutException, httpx.TransportError) as erro:
                falhas.append(f"{modelo}: {type(erro).__name__}")
                log.warning("Modelo %s sem resposta (%s); tentando o proximo", modelo, type(erro).__name__)
        raise IaIndisponivelError("Nenhum modelo respondeu: " + "; ".join(falhas))
