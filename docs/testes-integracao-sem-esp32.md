# Testes de integração

Executados em 18/11/2026 16:00 com `servico-iot-ia/avaliacao/testar_integracao.py`, contra os serviços locais e o broker broker.hivemq.com. ESP32 (Wokwi) online durante o teste: não.

| Grupo | Teste | Esperado | Obtido | Resultado |
|---|---|---|---|---|
| Backend | Login de USUARIO e ADMIN | token JWT | tokens recebidos | OK |
| Backend | USUARIO tentando cadastrar semaforo | HTTP 403 | HTTP 403 | OK |
| Backend | Proximidade a ~589 m | botao bloqueado | 589.33 m, desbloqueado=False | OK |
| Backend | Solicitacao longe do semaforo | HTTP 400, semaforo nao acionado | HTTP 400 | OK |
| Assistente | Pergunta respondivel pelo app/gateway | resposta com fontes | suficiente=True, fontes=4 | OK |
| Assistente | Pergunta fora da base | sem dados suficientes | suficiente=False | OK |
| Assistente | Pergunta sem token | HTTP 403 | HTTP 403 | OK |
| IoT | Servico IoT conectado ao broker | brokerConectado=true | {'brokerConectado': True} | OK |
| IoT | Segundos acima do limite | HTTP 400 sem publicar | HTTP 400 | OK |
| Falhas | ESP32 desligado | DISPOSITIVO_OFFLINE | SEM_CONFIRMACAO | FALHA |
| ESP32 | Fluxo completo com chuva (+10 s) | - | ESP32 offline no broker | NAO EXECUTADO |
| ESP32 | Pedidos simultaneos no mesmo semaforo | - | ESP32 offline no broker | NAO EXECUTADO |
| ESP32 | Solicitacao duplicada | - | ESP32 offline no broker | NAO EXECUTADO |
| ESP32 | Sequencia e tempos das fases | - | ESP32 offline no broker | NAO EXECUTADO |

Total: 9 OK, 1 falha(s), 4 não executado(s).
