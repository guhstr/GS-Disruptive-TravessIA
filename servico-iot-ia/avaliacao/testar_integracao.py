"""Testes de integracao do sistema completo (gateway, traffic-service, servico IoT, broker e ESP32).

Pre-requisitos: gateway (8080), traffic-service (8081) e servico-iot-ia (8083) em execucao,
usuarios de teste "maria_silva" (USUARIO) e "admin_gutemberg" (ADMIN) cadastrados.
Os testes que dependem do ESP32 so rodam se ele estiver online no broker; caso contrario,
aparecem como NAO EXECUTADO no relatorio.

Relatorio: docs/testes-integracao.md (ESP32 online) ou docs/testes-integracao-sem-esp32.md (ESP32 offline).

Uso: .venv/bin/python -m avaliacao.testar_integracao [--semaforo-chuva ID]
"""

import argparse
import json
import threading
import time

import httpx
import paho.mqtt.client as mqtt

from app.config import RAIZ_REPOSITORIO, carregar_configuracao

GATEWAY = "http://localhost:8080/api"
SERVICO_IOT = "http://localhost:8083/api"
config = carregar_configuracao()
BASE = config.mqtt_topico_base


class Observador:
    """Acompanha o estado do ESP32 e as fases publicadas no broker."""

    def __init__(self):
        self.online = None
        self.fases = []
        self._cliente = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._cliente.on_connect = lambda c, u, f, rc, p: c.subscribe(f"{BASE}/dispositivo/estado", 1)
        self._cliente.on_message = self._receber
        self._cliente.connect(config.mqtt_host, config.mqtt_porta)
        self._cliente.loop_start()

    def _receber(self, _c, _u, msg):
        if not msg.payload:
            return
        dados = json.loads(msg.payload)
        self.online = bool(dados.get("online"))
        fase = dados.get("fase")
        if fase and not msg.retain and (not self.fases or self.fases[-1][0] != fase):
            self.fases.append((fase, time.monotonic(), dados.get("extensaoPendente", 0), dados.get("tempoMs"),
                               dados.get("bootId")))


resultados = []


def registrar(grupo, nome, esperado, obtido, aprovado):
    status = "NAO EXECUTADO" if aprovado is None else ("OK" if aprovado else "FALHA")
    resultados.append((grupo, nome, esperado, obtido, status))
    print(f"[{status:13s}] {grupo} | {nome} | obtido: {obtido}")


def login(nome):
    r = httpx.post(f"{GATEWAY}/auth/login", json={"nome": nome}, timeout=30)
    return r.json()["usuario"], r.json()["token"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--semaforo-chuva", type=int, help="ID de um semaforo em local com chuva no momento")
    args = parser.parse_args()

    observador = Observador()
    limite = time.monotonic() + 15
    while observador.online is None and time.monotonic() < limite:
        time.sleep(0.2)
    dispositivo_online = observador.online is True

    usuario, token = login("maria_silva")
    _, token_admin = login("admin_gutemberg")
    h = {"Authorization": f"Bearer {token}"}
    registrar("Backend", "Login de USUARIO e ADMIN", "token JWT", "tokens recebidos", bool(token and token_admin))

    r = httpx.post(f"{GATEWAY}/semaforos", headers=h, timeout=30,
                   json={"descricao": "x", "latitude": 0, "longitude": 0, "ativo": True})
    registrar("Backend", "USUARIO tentando cadastrar semaforo", "HTTP 403", f"HTTP {r.status_code}", r.status_code == 403)

    semaforo = httpx.get(f"{GATEWAY}/semaforos/1", headers=h, timeout=30).json()
    lat, lon = semaforo["latitude"], semaforo["longitude"]
    longe = httpx.get(f"{GATEWAY}/semaforos/1/proximidade", headers=h, timeout=30,
                      params={"latitude": lat - 0.0053, "longitude": lon}).json()
    registrar("Backend", "Proximidade a ~589 m", "botao bloqueado",
              f"{longe['distanciaMetros']} m, desbloqueado={longe['botaoDesbloqueado']}", longe["botaoDesbloqueado"] is False)

    r = httpx.post(f"{GATEWAY}/solicitacoes", headers=h, timeout=30, json={
        "usuarioId": usuario["id"], "semaforoId": 1, "latitudeUsuario": lat - 0.0053, "longitudeUsuario": lon})
    registrar("Backend", "Solicitacao longe do semaforo", "HTTP 400, semaforo nao acionado",
              f"HTTP {r.status_code}", r.status_code == 400)

    r = httpx.post(f"{GATEWAY}/assistente/perguntas", headers=h, timeout=60,
                   json={"pergunta": "Quanto tempo a mais eu ganho na chuva?"}).json()
    registrar("Assistente", "Pergunta respondivel pelo app/gateway", "resposta com fontes",
              f"suficiente={r['contextoSuficiente']}, fontes={len(r['fontes'])}",
              r["contextoSuficiente"] and len(r["fontes"]) > 0)
    r = httpx.post(f"{GATEWAY}/assistente/perguntas", headers=h, timeout=60,
                   json={"pergunta": "Qual a capital da Franca?"}).json()
    registrar("Assistente", "Pergunta fora da base", "sem dados suficientes",
              f"suficiente={r['contextoSuficiente']}", r["contextoSuficiente"] is False)
    codigo = httpx.post(f"{GATEWAY}/assistente/perguntas", timeout=30, json={"pergunta": "teste"}).status_code
    registrar("Assistente", "Pergunta sem token", "HTTP 403", f"HTTP {codigo}", codigo == 403)

    status = httpx.get(f"{SERVICO_IOT}/iot/status", timeout=10).json()
    registrar("IoT", "Servico IoT conectado ao broker", "brokerConectado=true", str(status), status["brokerConectado"])
    r = httpx.post(f"{SERVICO_IOT}/iot/extensoes", timeout=10,
                   json={"solicitacaoId": 990001, "semaforoId": 1, "segundosExtras": 60})
    registrar("IoT", "Segundos acima do limite", "HTTP 400 sem publicar", f"HTTP {r.status_code}", r.status_code == 400)

    if not dispositivo_online:
        r = httpx.post(f"{GATEWAY}/solicitacoes", headers=h, timeout=100, json={
            "usuarioId": usuario["id"], "semaforoId": 1, "latitudeUsuario": lat, "longitudeUsuario": lon}).json()
        registrar("Falhas", "ESP32 desligado", "DISPOSITIVO_OFFLINE", r.get("statusDispositivo"),
                  r.get("statusDispositivo") == "DISPOSITIVO_OFFLINE")
        for nome in ("Fluxo completo com chuva (+10 s)", "Pedidos simultaneos no mesmo semaforo",
                     "Solicitacao duplicada", "Sequencia e tempos das fases"):
            registrar("ESP32", nome, "-", "ESP32 offline no broker", None)
    else:
        testar_com_dispositivo(h, usuario, args.semaforo_chuva, observador)

    salvar_relatorio(dispositivo_online)


def testar_com_dispositivo(h, usuario, semaforo_chuva, observador):
    alvo = semaforo_chuva or 1
    semaforo = httpx.get(f"{GATEWAY}/semaforos/{alvo}", headers=h, timeout=30).json()

    # Enquanto o pedido espera a confirmacao, o app mostra quanto falta para o sinal abrir.
    ate_abrir, aguardando = [], threading.Event()
    def acompanhar_abertura():
        while not aguardando.is_set():
            estado = httpx.get(f"{GATEWAY}/dispositivo/estado", headers=h, timeout=10).json()
            if estado.get("segundosAteAbrir") is not None:
                ate_abrir.append(estado["segundosAteAbrir"])
            aguardando.wait(1.0)
    observador_abertura = threading.Thread(target=acompanhar_abertura, daemon=True)
    observador_abertura.start()
    inicio = time.monotonic()
    r = httpx.post(f"{GATEWAY}/solicitacoes", headers=h, timeout=100, json={
        "usuarioId": usuario["id"], "semaforoId": alvo,
        "latitudeUsuario": semaforo["latitude"], "longitudeUsuario": semaforo["longitude"]}).json()
    status = r.get("statusDispositivo")
    restante = r.get("travessiaRestanteSegundos")
    if status == "ACEITO":
        # Com o Wokwi lento, a abertura pode passar do tempo de espera do servico: a resposta e ACEITO
        # e o app acompanha o estado do ESP32 ate o sinal abrir. O teste faz o mesmo.
        limite = time.monotonic() + 120
        while time.monotonic() < limite:
            estado = httpx.get(f"{GATEWAY}/dispositivo/estado", headers=h, timeout=10).json()
            if estado.get("pedestreAberto"):
                restante = estado["travessiaRestanteSegundos"]
                status = "ACEITO e depois aberto (acompanhado pelo estado do ESP32)"
                break
            time.sleep(0.5)
    aguardando.set()
    observador_abertura.join()
    registrar("ESP32", f"Fluxo completo app->ESP32 (semaforo #{alvo}, clima '{r.get('condicaoClimatica')}')",
              "EXECUTADO, ou ACEITO e o sinal abrindo em seguida, com os segundos decididos pelo backend",
              f"{status}, +{r.get('segundosExtras')} s, {time.monotonic() - inicio:.1f} s",
              status == "EXECUTADO" or status.startswith("ACEITO e depois aberto"))
    distintos = list(dict.fromkeys(ate_abrir))
    if len(distintos) >= 2:
        registrar("ESP32", "Contagem ate o sinal de pedestres abrir (pedido agendado)", "valores diminuindo",
                  f"leituras: {distintos}", distintos == sorted(distintos, reverse=True))
    else:
        registrar("ESP32", "Contagem ate o sinal de pedestres abrir (pedido agendado)", "valores diminuindo",
                  "pedido aplicado com o sinal ja aberto (sem espera)", None)
    maximo = 15 + (r.get("segundosExtras") or 0)
    registrar("ESP32", "Tempo restante de travessia devolvido ao app", f"entre 1 e {maximo} s",
              f"{restante} s", isinstance(restante, int) and 1 <= restante <= maximo)

    # O app acompanha a contagem pelo estado do ESP32 (relogio do dispositivo, igual ao LCD).
    leituras = []
    for _ in range(4):
        time.sleep(1.5)
        estado = httpx.get(f"{GATEWAY}/dispositivo/estado", headers=h, timeout=10).json()
        if estado.get("pedestreAberto"):
            leituras.append(estado["travessiaRestanteSegundos"])
    registrar("ESP32", "Contagem da travessia acompanhada pelo app (estado do ESP32 via gateway)",
              "sinal aberto e contagem diminuindo", f"leituras: {leituras}",
              len(leituras) >= 2 and leituras == sorted(leituras, reverse=True) and leituras[0] > leituras[-1])

    # Para os pedidos ficarem "em andamento" ao mesmo tempo, a travessia anterior precisa ter terminado:
    # com o sinal fechado, o ESP32 aceita e agenda o primeiro pedido, e o segundo chega durante a espera.
    limite = time.monotonic() + 90
    while time.monotonic() < limite:
        if not httpx.get(f"{GATEWAY}/dispositivo/estado", headers=h, timeout=10).json().get("pedestreAberto"):
            break
        time.sleep(1)
    pedido = {"solicitacaoId": 990100 + int(time.time()) % 1000, "semaforoId": 1, "segundosExtras": 5}
    respostas = {}

    def enviar(chave, corpo):
        respostas[chave] = httpx.post(f"{SERVICO_IOT}/iot/extensoes", json=corpo, timeout=60)
    primeira = threading.Thread(target=enviar, args=("primeira", pedido))
    primeira.start()
    time.sleep(0.5)
    enviar("simultanea", {**pedido, "solicitacaoId": pedido["solicitacaoId"] + 1})
    primeira.join()
    registrar("ESP32", "Pedidos simultaneos no mesmo semaforo", "segundo pedido HTTP 409",
              f"HTTP {respostas['simultanea'].status_code}", respostas["simultanea"].status_code == 409)

    repetida = httpx.post(f"{SERVICO_IOT}/iot/extensoes", json=pedido, timeout=60).json()
    original = respostas["primeira"].json()
    registrar("ESP32", "Solicitacao duplicada", "mesmo requestId, sem novo comando",
              f"{repetida['requestId'] == original['requestId']} ({original['status']})",
              repetida["requestId"] == original["requestId"])

    print("Observando um ciclo completo de fases (cerca de 40 s, ou mais se o Wokwi estiver lento)...")
    observador.fases.clear()
    limite = time.monotonic() + 150
    def fases_execucao_atual():
        return [f[0] for f in observador.fases if f[4] == observador.fases[-1][4]] if observador.fases else []
    while time.monotonic() < limite and fases_execucao_atual().count("TODOS_VERMELHO") < 3:
        time.sleep(0.5)
    # Se a simulacao reiniciar durante a observacao, so a execucao mais recente do ESP32 e considerada.
    fases = [f for f in observador.fases if f[4] == observador.fases[-1][4]] if observador.fases else []
    if len(fases) < len(observador.fases):
        print("Aviso: o ESP32 reiniciou durante a observacao; fases da execucao anterior descartadas")
    # Com o relogio do ESP32 (tempoMs) as duracoes ficam no tempo da simulacao; sem ele, no relogio real.
    relogio_esp32 = len(fases) > 1 and all(f[3] is not None for f in fases)
    duracoes = [(fases[i][0],
                 (fases[i + 1][3] - fases[i][3]) / 1000 if relogio_esp32 else fases[i + 1][1] - fases[i][1],
                 fases[i][2]) for i in range(len(fases) - 1)]
    # Transicoes permitidas: veiculos e pedestres sempre separados por "todos vermelhos".
    permitidas = {
        "TODOS_VERMELHO": {"VEICULOS_VERDE", "PEDESTRE_VERDE"},
        "VEICULOS_VERDE": {"VEICULOS_AMARELO"},
        "VEICULOS_AMARELO": {"TODOS_VERMELHO"},
        "PEDESTRE_VERDE": {"PEDESTRE_PISCANDO"},
        "PEDESTRE_PISCANDO": {"TODOS_VERMELHO"},
    }
    transicoes = [(fases[i][0], fases[i + 1][0]) for i in range(len(fases) - 1)]
    invalidas = [t for t in transicoes if t[1] not in permitidas.get(t[0], set())]
    texto = ", ".join(f"{n} {s:.1f}s" for n, s, _ in duracoes)
    registrar("ESP32", "Sequencia das fases (veiculos e pedestres separados por todos vermelhos)",
              "somente transicoes permitidas", texto if not invalidas else f"invalidas: {invalidas}",
              len(transicoes) >= 6 and not invalidas)

    # Sem o relogio do ESP32, a velocidade da simulacao e estimada pelas fases de veiculos,
    # que tem duracao fixa (o Wokwi pode simular mais devagar que o tempo real).
    nominal_veiculos = {"VEICULOS_VERDE": 10, "VEICULOS_AMARELO": 3}
    medidas = [(s, nominal_veiculos[n]) for n, s, _ in duracoes if n in nominal_veiculos]
    escala = 1.0
    if not relogio_esp32 and medidas:
        escala = sum(s for s, _ in medidas) / sum(n for _, n in medidas)

    for i in range(1, len(duracoes) - 1):
        if duracoes[i][0] == "PEDESTRE_VERDE" and duracoes[i + 1][0] == "PEDESTRE_PISCANDO":
            extra = duracoes[i - 1][2]
            travessia = duracoes[i][1] + duracoes[i + 1][1]
            corrigida = travessia / escala
            registrar("ESP32", "Tempo de travessia de pedestres", f"{15 + extra} s (15 s padrao + {extra} s extra), +-1 s",
                      f"{corrigida:.1f} s medidos no relogio do ESP32" if relogio_esp32 else
                      f"{corrigida:.1f} s no tempo da simulacao ({travessia:.1f} s no relogio real, "
                      f"simulacao a {100 / escala:.0f}% da velocidade real)",
                      abs(corrigida - (15 + extra)) <= 1.0)
            break
    else:
        registrar("ESP32", "Tempo de travessia de pedestres", "15 s padrao", "fase de pedestres nao observada", False)


def salvar_relatorio(dispositivo_online):
    linhas = [
        "# Testes de integração",
        "",
        f"Executados em {time.strftime('%d/%m/%Y %H:%M')} com `servico-iot-ia/avaliacao/testar_integracao.py`, "
        f"contra os serviços locais e o broker {config.mqtt_host}. ESP32 (Wokwi) online durante o teste: "
        f"{'sim' if dispositivo_online else 'não'}.",
        "",
        "| Grupo | Teste | Esperado | Obtido | Resultado |",
        "|---|---|---|---|---|",
        *[f"| {g} | {n} | {e} | {str(o).replace('|', '/')} | {s} |" for g, n, e, o, s in resultados],
        "",
        f"Total: {sum(r[4] == 'OK' for r in resultados)} OK, {sum(r[4] == 'FALHA' for r in resultados)} falha(s), "
        f"{sum(r[4] == 'NAO EXECUTADO' for r in resultados)} não executado(s).",
        "",
    ]
    # Com o ESP32 desligado o relatorio vai para outro arquivo, para nao sobrescrever o teste completo.
    nome = "testes-integracao.md" if dispositivo_online else "testes-integracao-sem-esp32.md"
    destino = RAIZ_REPOSITORIO / "docs" / nome
    destino.write_text("\n".join(linhas), encoding="utf-8")
    print(f"Relatorio salvo em {destino}")


if __name__ == "__main__":
    main()
