"""Avaliacao da IA generativa do projeto (assistente de duvidas e orientacao depois do pedido).

Metricas do assistente (casos em casos_rag.json):
- Recuperacao Hit@1 / Hit@k: o documento esperado aparece no 1o trecho / entre os k recuperados
  (apenas perguntas respondiveis), comparando a busca vetorial com a busca hibrida.
- Respostas corretas: a resposta foi dada (nao recusada) e contem os fatos esperados.
- Recusa correta: perguntas fora da base recebem a mensagem de falta de dados.
- Falsas recusas: perguntas respondiveis que foram recusadas.
- Conversa: perguntas de acompanhamento (com historico) respondidas corretamente.
- Fidelidade: um modelo avaliador, diferente do que gera as respostas, confere se cada
  afirmacao da resposta esta apoiada nos trechos recuperados (LLM como avaliador).

Metricas da orientacao (casos_orientacao.json): gerada pela IA, segundos corretos e fidelidade.

Uso: .venv/bin/python -m avaliacao.avaliar_rag  (gera docs/avaliacao-rag.md)
"""

import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path

from app.config import RAIZ_REPOSITORIO
from app.faq.assistente import AssistenteFaq, MensagemHistorico
from app.ia.cliente_gemini import ClienteGemini, IaIndisponivelError

PASTA = Path(__file__).parent

# O avaliador usa modelos diferentes do gerador (gemini-3.5-flash-lite) para reduzir o vies de autoavaliacao.
MODELOS_AVALIADOR = [m.strip() for m in os.getenv(
    "GEMINI_MODELOS_AVALIADOR",
    "gemini-3.1-flash-lite,gemini-3-flash-preview,gemini-3.5-flash,gemini-3.6-flash,gemini-flash-latest,"
    "gemini-pro-latest"
).split(",") if m.strip()]

INSTRUCOES_AVALIADOR = """Você avalia se um TEXTO gerado por IA está totalmente apoiado no CONTEXTO.
Liste as afirmações do TEXTO que NÃO estão no CONTEXTO nem nos DADOS DO PEDIDO (informações novas,
números, regras ou recomendações diferentes). Ignore o estilo, a ordem das frases e as marcações como [1].
Informações que vêm dos DADOS DO PEDIDO (por exemplo, os segundos ganhos, o clima e o período) são apoiadas.
Sinônimos e reformulações do CONTEXTO também são apoiados (por exemplo, garoa é um tipo de chuva).
Responda somente com JSON no formato {"fiel": true ou false, "sem_apoio": ["afirmação", ...]}."""


def normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def avaliar_fidelidade(cliente: ClienteGemini, contexto: list, texto: str, dados_pedido: str = "") -> dict:
    """Devolve {"fiel": bool|None, "sem_apoio": [...]}; fiel=None quando o avaliador nao respondeu.
    Se todos os modelos estiverem sem cota, espera e tenta mais uma vez (limite por minuto do plano gratuito)."""
    mensagens = [
        {"role": "system", "content": INSTRUCOES_AVALIADOR},
        {"role": "user", "content": "CONTEXTO:\n" + "\n\n".join(contexto)
         + (f"\n\nDADOS DO PEDIDO: {dados_pedido}" if dados_pedido else "")
         + f"\n\nTEXTO:\n{texto}"},
    ]
    try:
        try:
            resposta = cliente.gerar(mensagens, temperatura=0.0, modelos=MODELOS_AVALIADOR)
        except IaIndisponivelError:
            time.sleep(60)
            resposta = cliente.gerar(mensagens, temperatura=0.0, modelos=MODELOS_AVALIADOR)
        bruto = re.search(r"\{.*\}", resposta.conteudo, re.S)
        dados = json.loads(bruto.group(0)) if bruto else {}
        return {"fiel": bool(dados["fiel"]) if "fiel" in dados else None,
                "sem_apoio": [str(a) for a in dados.get("sem_apoio", [])], "modelo": resposta.modelo}
    except (IaIndisponivelError, json.JSONDecodeError) as erro:
        logging.warning("Avaliador indisponivel: %s", erro)
        return {"fiel": None, "sem_apoio": [], "modelo": None}


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "-"


def main():
    logging.basicConfig(level=logging.WARNING)
    cliente = ClienteGemini()
    casos = json.loads((PASTA / "casos_rag.json").read_text(encoding="utf-8"))
    casos_orientacao = json.loads((PASTA / "casos_orientacao.json").read_text(encoding="utf-8"))
    assistente = AssistenteFaq(
        cliente,
        RAIZ_REPOSITORIO / "base-conhecimento",
        RAIZ_REPOSITORIO / "servico-iot-ia" / "dados" / "indice_rag.json",
        float(os.getenv("RAG_LIMIAR_SIMILARIDADE", "0.62")),
        int(os.getenv("RAG_QUANTIDADE_TRECHOS", "4")),
        os.getenv("RAG_MODO_BUSCA", "vetorial"),
    )
    indice = assistente.preparar()

    # ---------------- Assistente de duvidas ----------------
    linhas, resultados, sem_apoio = [], [], []
    for caso in casos:
        historico = [MensagemHistorico(m["papel"], m["texto"]) for m in caso.get("historico", [])]
        inicio = time.monotonic()
        resposta = assistente.responder(caso["pergunta"], historico)
        duracao = time.monotonic() - inicio
        respondivel = caso["documento"] is not None
        busca = {}
        for modo in ("vetorial", "hibrida"):
            documentos = [r.trecho.documento for r in assistente.recuperar(resposta.pergunta_considerada, modo=modo)]
            busca[modo] = (respondivel and documentos[0] == caso["documento"],
                           respondivel and caso["documento"] in documentos)
        # Cada fato pode ter alternativas separadas por "|" (ex.: "rampa|rebaixamento").
        fatos_ok = all(any(normalizar(a) in normalizar(resposta.resposta) for a in f.split("|"))
                       for f in caso["fatos"])
        correto = (resposta.contexto_suficiente and fatos_ok) if respondivel else not resposta.contexto_suficiente
        fidelidade = (avaliar_fidelidade(cliente, resposta.contexto, resposta.resposta)
                      if resposta.contexto_suficiente else {"fiel": None, "sem_apoio": []})
        if fidelidade["fiel"] is False:
            sem_apoio.append((caso["pergunta"], fidelidade["sem_apoio"]))
        resultados.append({"respondivel": respondivel, "busca": busca, "conversa": bool(historico),
                           "correto": correto, "recusou": not resposta.contexto_suficiente,
                           "fiel": fidelidade["fiel"], "duracao": duracao,
                           "sugestoes": len(resposta.sugestoes)})
        pergunta = caso["pergunta"]
        if historico:
            pergunta = (f"(após \"{historico[-2].texto}\") {pergunta} "
                        f"-> entendida como: {resposta.pergunta_considerada}")
        fiel_txt = {True: "sim", False: "não", None: "-"}[fidelidade["fiel"]]
        linhas.append(
            f"| {pergunta} | {'sim' if respondivel else 'não'} | "
            f"{'-' if resposta.maior_similaridade is None else f'{resposta.maior_similaridade:.3f}'} | "
            f"{'sim' if busca['hibrida'][1] else ('-' if not respondivel else 'não')} | "
            f"{'recusou' if resposta.contexto_suficiente is False else 'respondeu'} | {fiel_txt} | "
            f"{'OK' if correto else 'FALHA'} | {resposta.resposta.replace('|', '/')} |")
        print(f"{'OK   ' if correto else 'FALHA'} fiel={fiel_txt:3s} {caso['pergunta']}")
        time.sleep(1)  # respeita o limite por minuto do plano gratuito do Gemini

    resp = [r for r in resultados if r["respondivel"]]
    fora = [r for r in resultados if not r["respondivel"]]
    conversa = [r for r in resultados if r["conversa"]]
    respondidas = [r for r in resultados if not r["recusou"]]
    avaliadas = [r for r in respondidas if r["fiel"] is not None]
    metricas = [
        ("Respostas corretas com os fatos esperados", pct(sum(r["correto"] for r in resp), len(resp))),
        ("Falsas recusas (respondíveis recusadas)", pct(sum(r["recusou"] for r in resp), len(resp))),
        ("Recusa correta (fora da base)", pct(sum(r["correto"] for r in fora), len(fora))),
        ("Perguntas de acompanhamento corretas (com histórico)",
         pct(sum(r["correto"] for r in conversa), len(conversa))),
        ("Acerto geral", pct(sum(r["correto"] for r in resultados), len(resultados))),
        ("Fidelidade ao contexto (LLM avaliador, respostas dadas)",
         pct(sum(r["fiel"] for r in avaliadas), len(avaliadas))),
        ("Respostas com sugestões de perguntas", pct(sum(r["sugestoes"] > 0 for r in respondidas), len(respondidas))),
        ("Tempo médio por pergunta (resposta + sugestões)",
         f"{sum(r['duracao'] for r in resultados) / len(resultados):.1f} s"),
    ]
    comparacao = [
        f"| {nome} | {pct(sum(r['busca'][modo][0] for r in resp), len(resp))} | "
        f"{pct(sum(r['busca'][modo][1] for r in resp), len(resp))} |"
        for nome, modo in (("Vetorial (somente embeddings)", "vetorial"),
                           ("Híbrida (embeddings + BM25, fusão RRF)", "hibrida"))]

    # ---------------- Orientacao depois do pedido ----------------
    linhas_orientacao, orientacoes = [], []
    for caso in casos_orientacao:
        orientacao = assistente.orientar(caso["clima"], caso["segundos"], caso["periodo"])
        dados = (f"{caso['segundos']} segundos extras concedidos; clima: {caso['clima']}; período: {caso['periodo']}; "
                 "regra do sistema: +5 s com tempo seco e +10 s com chuva")
        fidelidade = (avaliar_fidelidade(cliente, orientacao.contexto, orientacao.mensagem, dados)
                      if orientacao.gerada_por_ia else {"fiel": None, "sem_apoio": []})
        segundos_ok = re.search(rf"(?<!\d){caso['segundos']}(?!\d)", orientacao.mensagem) is not None
        orientacoes.append({"ia": orientacao.gerada_por_ia, "segundos": segundos_ok, "fiel": fidelidade["fiel"]})
        if fidelidade["fiel"] is False:
            sem_apoio.append((f"Orientação: {caso['clima']} ({caso['periodo']})", fidelidade["sem_apoio"]))
        fiel_txt = {True: "sim", False: "não", None: "-"}[fidelidade["fiel"]]
        documentos = ", ".join(sorted({f.documento for f in orientacao.fontes})) or "-"
        linhas_orientacao.append(
            f"| {caso['clima']} | {caso['periodo']} | +{caso['segundos']} s | "
            f"{'IA' if orientacao.gerada_por_ia else 'texto padrão'} | {documentos} | {fiel_txt} | "
            f"{orientacao.mensagem.replace('|', '/')} |")
        print(f"Orientacao {caso['clima']}/{caso['periodo']}: ia={orientacao.gerada_por_ia} fiel={fiel_txt}")
    avaliadas_orientacao = [o for o in orientacoes if o["fiel"] is not None]
    metricas_orientacao = [
        ("Orientações geradas pela IA", pct(sum(o["ia"] for o in orientacoes), len(orientacoes))),
        ("Orientações com os segundos corretos", pct(sum(o["segundos"] for o in orientacoes), len(orientacoes))),
        ("Fidelidade ao contexto (LLM avaliador)",
         pct(sum(o["fiel"] for o in avaliadas_orientacao), len(avaliadas_orientacao))),
    ]

    relatorio = [
        "# Avaliação da IA generativa",
        "",
        f"Executada em {time.strftime('%d/%m/%Y %H:%M')} com o modelo de embedding `{indice.modelo}`"
        + ("" if assistente._indice.modelo == indice.modelo else
           f" (trocado durante a execução para `{assistente._indice.modelo}` por falta de cota)") + ", "
        f"{len(indice.trechos)} trechos, limiar de similaridade {assistente.limiar}, {assistente.quantidade} "
        f"trechos recuperados e busca `{assistente.modo_busca}`. Avaliador de fidelidade: modelos "
        f"`{', '.join(MODELOS_AVALIADOR)}` (o primeiro disponível), diferentes do modelo que gera as respostas. "
        "Gerado por `servico-iot-ia/avaliacao/avaliar_rag.py` a partir de `casos_rag.json` e `casos_orientacao.json`.",
        "",
        "## Assistente de dúvidas",
        "",
        "| Métrica | Resultado |",
        "|---|---|",
        *[f"| {nome} | {valor} |" for nome, valor in metricas],
        "",
        "### Busca vetorial x busca híbrida (perguntas respondíveis)",
        "",
        "| Busca | Hit@1 | Hit@4 |",
        "|---|---|---|",
        *comparacao,
        "",
        "Critério de resposta correta: para perguntas respondíveis, o assistente responde (não recusa) e o texto "
        "contém os fatos esperados do caso; para perguntas fora da base, o assistente informa que não tem dados "
        "suficientes. Nas perguntas de acompanhamento, a conversa anterior é enviada junto e a recuperação usa a "
        "pergunta reescrita pela IA (coluna Pergunta). Fidelidade: o avaliador recebe os trechos enviados ao modelo "
        "e a resposta, e lista as afirmações sem apoio nos trechos.",
        "",
        "## Orientação depois do pedido",
        "",
        "| Métrica | Resultado |",
        "|---|---|",
        *[f"| {nome} | {valor} |" for nome, valor in metricas_orientacao],
        "",
        "| Clima | Período | Extra | Origem | Documentos usados | Fiel | Mensagem |",
        "|---|---|---|---|---|---|---|",
        *linhas_orientacao,
        "",
        "## Afirmações sem apoio apontadas pelo avaliador",
        "",
        *([f"- **{origem}:** " + "; ".join(itens or ["(sem detalhes)"]) for origem, itens in sem_apoio]
          or ["Nenhuma."]),
        "",
        "## Resultados por pergunta",
        "",
        "| Pergunta | Respondível | Maior similaridade | Documento esperado recuperado | Comportamento | Fiel | "
        "Avaliação | Resposta |",
        "|---|---|---|---|---|---|---|---|",
        *linhas,
        "",
    ]
    destino = RAIZ_REPOSITORIO / "docs" / "avaliacao-rag.md"
    destino.write_text("\n".join(relatorio), encoding="utf-8")
    print("\n".join(f"{n}: {v}" for n, v in metricas + metricas_orientacao))
    print("\n".join(comparacao))
    print(f"Relatorio salvo em {destino}")


if __name__ == "__main__":
    main()
