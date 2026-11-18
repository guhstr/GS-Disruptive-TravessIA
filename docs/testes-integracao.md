# Testes de integração

Executados em 18/11/2026 19:05 com `servico-iot-ia/avaliacao/testar_integracao.py`, contra os serviços locais e o broker broker.hivemq.com. ESP32 (Wokwi) online durante o teste: sim.

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
| ESP32 | Fluxo completo app->ESP32 (semaforo #26, clima 'Chuva leve') | EXECUTADO, ou ACEITO e o sinal abrindo em seguida, com os segundos decididos pelo backend | EXECUTADO, +10 s, 27.0 s | OK |
| ESP32 | Contagem ate o sinal de pedestres abrir (pedido agendado) | valores diminuindo | leituras: [15, 9, 8, 7, 6, 5, 4, 3, 2, 1] | OK |
| ESP32 | Tempo restante de travessia devolvido ao app | entre 1 e 25 s | 25 s | OK |
| ESP32 | Contagem da travessia acompanhada pelo app (estado do ESP32 via gateway) | sinal aberto e contagem diminuindo | leituras: [24, 24, 23, 22] | OK |
| ESP32 | Pedidos simultaneos no mesmo semaforo | segundo pedido HTTP 409 | HTTP 409 | OK |
| ESP32 | Solicitacao duplicada | mesmo requestId, sem novo comando | True (EXECUTADO) | OK |
| ESP32 | Sequencia das fases (veiculos e pedestres separados por todos vermelhos) | somente transicoes permitidas | PEDESTRE_VERDE 16.0s, PEDESTRE_PISCANDO 4.0s, TODOS_VERMELHO 2.0s, VEICULOS_VERDE 10.0s, VEICULOS_AMARELO 3.0s, TODOS_VERMELHO 2.0s, PEDESTRE_VERDE 11.0s, PEDESTRE_PISCANDO 4.0s | OK |
| ESP32 | Tempo de travessia de pedestres | 15 s (15 s padrao + 0 s extra), +-1 s | 15.0 s medidos no relogio do ESP32 | OK |

Total: 17 OK, 0 falha(s), 0 não executado(s).
