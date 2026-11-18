"""Guardrails do assistente: o chat so fala do Travessia Inteligente e da seguranca na travessia.

Camadas (da mais barata para a mais cara):
1. Entrada: regras que bloqueiam injecao de prompt, troca de papel, pedido das instrucoes,
   pedidos de codigo, de dados pessoais e de uso indevido do sistema (sem chamar a IA).
2. Escopo: limiar de similaridade com a base e, na faixa duvidosa, um classificador de escopo (IA).
3. Instrucoes do modelo: responder so com o contexto, citar fontes e recusar o resto.
4. Saida: a resposta nao pode vazar as instrucoes, trazer codigo ou links, nem citar numeros
   que nao estejam nos trechos recuperados ou na pergunta.
"""

import re
import unicodedata
from typing import Iterable, Optional

RESPOSTA_FORA_DO_ESCOPO = ("Só posso ajudar com dúvidas sobre o aplicativo Travessia Inteligente e sobre "
                           "segurança na travessia de pedestres.")

# Motivos de recusa devolvidos pela API (campo motivoRecusa).
BLOQUEIO_SEGURANCA = "bloqueado_seguranca"
FORA_DO_ESCOPO = "fora_do_escopo"
SEM_DADOS = "sem_dados"
RESPOSTA_SEM_APOIO = "resposta_sem_apoio"

_PADROES_ENTRADA = [
    # Injecao de prompt e troca de papel
    r"\b(ignor|desconsider|esquec|desobedec|burl)\w*\s+(\w+\s+){0,4}(instruc|restric|diretriz|prompt)",
    r"\b(ignor|desconsider|esquec|desobedec|burl)\w*\s+(\w+\s+){0,2}(suas|tuas)?\s*regras\s+"
    r"(anteriores|acima|dadas|do\s+sistema|que\s+(te|lhe|voce)|deste|desse|suas)",
    r"\b(ignor|desconsider|esquec)\w*\s+(as\s+)?(suas|tuas)\s+regras",
    r"\b(prompt|instruc\w*|mensagem|configurac\w*)\s+(\w+\s+){0,2}(do|de)\s+sistema\b",
    r"\bsystem\s*prompt\b|\bjailbreak\b|\bprompt\s+injection\b",
    r"\b(revel|mostr|repit|imprim|list|copi|exib)\w*\s+(\w+\s+){0,4}(instruc|regras|prompt|configurac)",
    r"\b(aja|atue|finja|fingir|comporte-se|se\s+comporte|interprete|simule)\s+(\w+\s+){0,2}(como|que|ser)\b",
    r"\b(voce|vc)\s+(agora\s+)?(e|eh|sera|vai\s+ser)\s+(um|uma|o|a)\s+(outr|nov|assistente|ia|chatbot|personagem|hacker)",
    r"\bmodo\s+(desenvolvedor|developer|deus|irrestrito|livre|sem\s+(filtro|restric))",
    r"\b(ignore|disregard|forget)\s+(all|any|the|previous|prior|your)\b|\byou\s+are\s+now\b|\bact\s+as\b|\bpretend\b",
    # Pedidos claramente fora do proposito do assistente
    r"\b(codigo|script|programa|funcao|query)\s+(\w+\s+){0,3}(python|java|javascript|sql|html|c\+\+|kotlin)\b",
    r"```",
    r"\b(cpf|rg|senha|token|chave\s+(de\s+)?api|e-?mail|telefone|endereco)s?\b(\s+\w+){0,6}\s+(dos?|das?|de)\s+"
    r"(usuari|pessoa|cadastrad|cliente|integrante|aluno)",
    r"\b(burlar|hackear|invadir|sabotar|fraudar|desligar|derrubar|manipular|falsificar)\b(\s+\w+){0,5}\s+"
    r"(semaforo|sistema|aplicativo|app|servidor|gps|backend|broker)",
]
_REGEX_ENTRADA = [re.compile(p) for p in _PADROES_ENTRADA]

# Trechos das instrucoes internas que nunca devem aparecer em uma resposta.
_MARCAS_INSTRUCOES = ("regras:", "contexto:", "modo linguagem simples", "pergunta ja feita", "ultima pergunta",
                      "use somente as informacoes", "responda exatamente")

_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")
_CITACAO = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.split())


def verificar_entrada(texto: str) -> Optional[str]:
    """Devolve BLOQUEIO_SEGURANCA quando o texto tenta mudar as regras ou pede algo fora do proposito."""
    normalizado = normalizar(texto)
    if any(regex.search(normalizado) for regex in _REGEX_ENTRADA):
        return BLOQUEIO_SEGURANCA
    return None


def numeros(texto: str) -> set:
    return {n.replace(",", ".") for n in _NUMERO.findall(_CITACAO.sub(" ", texto))}


def verificar_resposta(resposta: str, contexto: Iterable[str], pergunta: str) -> Optional[str]:
    """Confere a resposta gerada antes de ela chegar ao app."""
    normalizada = normalizar(resposta)
    if any(marca in normalizada for marca in _MARCAS_INSTRUCOES):
        return BLOQUEIO_SEGURANCA
    if "```" in resposta or re.search(r"https?://|www\.", normalizada):
        return BLOQUEIO_SEGURANCA
    # Todo numero citado precisa estar nos trechos recuperados ou na propria pergunta.
    permitidos = numeros(" ".join(contexto)) | numeros(pergunta)
    if numeros(resposta) - permitidos:
        return RESPOSTA_SEM_APOIO
    return None


def clima_valido(texto: str) -> bool:
    """A condicao climatica vem do app: so texto curto, sem comandos para a IA."""
    return (bool(re.fullmatch(r"[\w\sÀ-ÿ,.()\-/]{1,100}", texto.strip()))
            and verificar_entrada(texto) is None)
