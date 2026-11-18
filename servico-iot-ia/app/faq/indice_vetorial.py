"""Indice vetorial em memoria, salvo em disco para evitar recalcular embeddings.

O arquivo guarda o modelo de embedding usado e a assinatura da base. Se a base
mudar, ou se for preciso trocar de modelo, o indice e reconstruido.
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

from app.faq.base_conhecimento import Trecho, assinatura
from app.ia.cliente_gemini import ClienteGemini

log = logging.getLogger(__name__)


@dataclass
class TrechoEncontrado:
    trecho: Trecho
    similaridade: float


class IndiceVetorial:
    def __init__(self, trechos: List[Trecho], vetores: np.ndarray, modelo: str, assinatura_base: str):
        self.trechos = trechos
        self.modelo = modelo
        self.assinatura_base = assinatura_base
        normas = np.linalg.norm(vetores, axis=1, keepdims=True)
        self._vetores = vetores / np.where(normas == 0, 1, normas)

    @classmethod
    def construir(cls, trechos: List[Trecho], cliente: ClienteGemini,
                  modelos: Optional[List[str]] = None) -> "IndiceVetorial":
        resultado = cliente.embeddings([t.texto_para_embedding for t in trechos], modelos)
        log.info("Indice RAG construido: %d trechos com o modelo %s", len(trechos), resultado.modelo)
        return cls(trechos, np.array(resultado.vetores, dtype=np.float32), resultado.modelo,
                   assinatura(trechos))

    @classmethod
    def carregar(cls, arquivo: Path, trechos: List[Trecho]) -> Optional["IndiceVetorial"]:
        if not arquivo.exists():
            return None
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        if dados.get("assinatura") != assinatura(trechos):
            log.info("Base de conhecimento alterada; o indice sera reconstruido")
            return None
        salvos = [Trecho(**t) for t in dados["trechos"]]
        return cls(salvos, np.array(dados["vetores"], dtype=np.float32), dados["modelo"], dados["assinatura"])

    def salvar(self, arquivo: Path) -> None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps({
            "modelo": self.modelo,
            "assinatura": self.assinatura_base,
            "trechos": [asdict(t) for t in self.trechos],
            "vetores": self._vetores.round(6).tolist(),
        }), encoding="utf-8")

    def similaridades(self, vetor_pergunta: List[float]) -> np.ndarray:
        """Similaridade de cosseno da pergunta com todos os trechos."""
        consulta = np.array(vetor_pergunta, dtype=np.float32)
        consulta /= np.linalg.norm(consulta) or 1.0
        return self._vetores @ consulta
