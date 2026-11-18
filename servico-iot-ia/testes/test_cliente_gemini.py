import httpx
import pytest

from app.ia.cliente_gemini import ClienteGemini, IaIndisponivelError


def cliente_com_respostas(respostas_por_modelo):
    chamados = []

    def responder(request: httpx.Request):
        modelo = __import__("json").loads(request.content)["model"]
        chamados.append(modelo)
        status = respostas_por_modelo.get(modelo, 200)
        if status != 200:
            return httpx.Response(status, text="erro simulado")
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": f"ok {modelo}"}}]})

    cliente = ClienteGemini(chave="teste", modelos_chat=["m1", "m2", "m3"], modelos_embedding=["e1", "e2"],
                            transporte=httpx.MockTransport(responder))
    return cliente, chamados


def test_usa_o_primeiro_modelo_quando_ele_responde():
    cliente, chamados = cliente_com_respostas({})
    assert cliente.gerar([{"role": "user", "content": "oi"}]).modelo == "m1"
    assert chamados == ["m1"]


def test_cota_esgotada_passa_para_o_proximo_modelo():
    cliente, chamados = cliente_com_respostas({"m1": 429, "m2": 503})
    resposta = cliente.gerar([{"role": "user", "content": "oi"}])
    assert resposta.modelo == "m3" and resposta.conteudo == "ok m3"
    assert chamados == ["m1", "m2", "m3"]


def test_modelo_inexistente_passa_para_o_proximo_tambem_no_embedding():
    cliente, chamados = cliente_com_respostas({"e1": 404})
    resultado = cliente.embeddings(["texto"])
    assert resultado.vetores == [[0.1, 0.2]] and resultado.modelo == "e2"
    assert chamados == ["e1", "e2"]


def test_chave_invalida_interrompe_sem_tentar_outros_modelos():
    cliente, chamados = cliente_com_respostas({"m1": 403})
    with pytest.raises(IaIndisponivelError, match="Chave"):
        cliente.gerar([{"role": "user", "content": "oi"}])
    assert chamados == ["m1"]


def test_todos_os_modelos_falhando_gera_erro_com_o_historico():
    cliente, _ = cliente_com_respostas({"m1": 429, "m2": 429, "m3": 429})
    with pytest.raises(IaIndisponivelError, match="m1: HTTP 429; m2: HTTP 429; m3: HTTP 429"):
        cliente.gerar([{"role": "user", "content": "oi"}])


def test_sem_chave_configurada_nao_faz_requisicao():
    cliente = ClienteGemini(chave="", modelos_chat=["m1"])
    with pytest.raises(IaIndisponivelError, match="GEMINI_API_KEY"):
        cliente.gerar([{"role": "user", "content": "oi"}])
