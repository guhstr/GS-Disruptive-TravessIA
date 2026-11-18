"""Leitura da base de conhecimento (Markdown) e divisao em trechos para o RAG.

Cada documento e dividido pelas secoes "## ". Secoes longas sao quebradas em
partes de ate TAMANHO_MAXIMO caracteres, com o ultimo paragrafo repetido no
inicio da parte seguinte (sobreposicao), para nao perder contexto na fronteira.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List

TAMANHO_MAXIMO = 900


@dataclass(frozen=True)
class Trecho:
    documento: str
    titulo: str
    secao: str
    texto: str

    @property
    def texto_para_embedding(self) -> str:
        return f"{self.titulo} - {self.secao}\n{self.texto}"


def _dividir_em_partes(paragrafos: List[str]) -> List[str]:
    partes, atual = [], []
    for paragrafo in paragrafos:
        if atual and len("\n".join(atual + [paragrafo])) > TAMANHO_MAXIMO:
            partes.append("\n".join(atual))
            atual = [atual[-1]]
        atual.append(paragrafo)
    if atual:
        partes.append("\n".join(atual))
    return partes


def dividir_documento(nome: str, conteudo: str) -> List[Trecho]:
    titulo = nome
    secoes = []
    secao_atual, linhas = "Introducao", []
    for linha in conteudo.splitlines():
        if linha.startswith("# "):
            titulo = linha[2:].strip()
        elif linha.startswith("## "):
            if linhas:
                secoes.append((secao_atual, linhas))
            secao_atual, linhas = linha[3:].strip(), []
        elif linha.strip():
            linhas.append(linha.strip())
    if linhas:
        secoes.append((secao_atual, linhas))

    trechos = []
    for secao, paragrafos in secoes:
        for parte in _dividir_em_partes(paragrafos):
            trechos.append(Trecho(nome, titulo, secao, parte))
    return trechos


def carregar_trechos(diretorio: Path) -> List[Trecho]:
    trechos = []
    for arquivo in sorted(diretorio.glob("*.md")):
        trechos.extend(dividir_documento(arquivo.name, arquivo.read_text(encoding="utf-8")))
    return trechos


def assinatura(trechos: List[Trecho]) -> str:
    """Hash do conteudo: muda quando a base de conhecimento e editada."""
    h = hashlib.sha256()
    for t in trechos:
        h.update(t.texto_para_embedding.encode("utf-8"))
    return h.hexdigest()
