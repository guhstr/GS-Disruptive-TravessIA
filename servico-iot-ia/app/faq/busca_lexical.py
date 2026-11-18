"""Busca por palavras (BM25) e fusao com a busca vetorial.

A busca vetorial encontra trechos com o mesmo sentido, mesmo com palavras diferentes.
A busca por palavras acerta melhor termos exatos, como "192", "Lei 13.146" ou "PCD".
A busca hibrida combina as duas posicoes com Reciprocal Rank Fusion (RRF).
"""

import math
import re
import unicodedata
from collections import Counter
from typing import List, Sequence

# Palavras muito comuns que nao ajudam a diferenciar os trechos.
PALAVRAS_IGNORADAS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos", "em", "no", "na",
    "nos", "nas", "por", "para", "pra", "com", "sem", "e", "ou", "que", "se", "eu", "voce", "ele", "ela",
    "me", "meu", "minha", "seu", "sua", "ao", "aos", "como", "qual", "quais", "quando", "onde", "quanto",
    "quantos", "ser", "esta", "estou", "tem", "ter", "isso", "esse", "essa", "mais", "muito", "ja",
}

# Constante padrao do RRF: reduz o peso das posicoes mais baixas de cada ranking.
CONSTANTE_RRF = 60


def tokenizar(texto: str) -> List[str]:
    sem_acento = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return [t for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", sem_acento) if t not in PALAVRAS_IGNORADAS]


class BuscaLexical:
    """BM25 sobre os trechos da base de conhecimento."""

    def __init__(self, textos: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self._k1, self._b = k1, b
        self._documentos = [Counter(tokenizar(t)) for t in textos]
        self._tamanhos = [sum(d.values()) for d in self._documentos]
        self._tamanho_medio = (sum(self._tamanhos) / len(self._tamanhos)) if self._tamanhos else 0.0
        total = len(self._documentos)
        frequencia = Counter(termo for d in self._documentos for termo in d)
        self._idf = {termo: math.log(1 + (total - n + 0.5) / (n + 0.5)) for termo, n in frequencia.items()}

    def pontuar(self, consulta: str) -> List[float]:
        termos = tokenizar(consulta)
        pontuacoes = []
        for documento, tamanho in zip(self._documentos, self._tamanhos):
            total = 0.0
            for termo in termos:
                frequencia = documento.get(termo, 0)
                if frequencia:
                    normalizacao = 1 - self._b + self._b * tamanho / (self._tamanho_medio or 1)
                    total += self._idf[termo] * frequencia * (self._k1 + 1) / (frequencia + self._k1 * normalizacao)
            pontuacoes.append(total)
        return pontuacoes


def fundir_rankings(*pontuacoes: Sequence[float]) -> List[int]:
    """Ordena os trechos pela soma de 1 / (k + posicao) em cada ranking (Reciprocal Rank Fusion)."""
    soma = [0.0] * len(pontuacoes[0])
    for lista in pontuacoes:
        ordem = sorted(range(len(lista)), key=lambda i: -lista[i])
        for posicao, indice in enumerate(ordem, start=1):
            soma[indice] += 1 / (CONSTANTE_RRF + posicao)
    return sorted(range(len(soma)), key=lambda i: -soma[i])
