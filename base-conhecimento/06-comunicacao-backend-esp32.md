# Comunicação entre o backend e o ESP32 (MQTT)

## Visão geral do fluxo
Aplicativo, gateway Java, serviço de tráfego Java, serviço IoT em Python, broker MQTT, ESP32, e o caminho de volta até o aplicativo. O serviço IoT publica o comando no broker e aguarda a confirmação do ESP32.

## Broker
É usado o broker público HiveMQ (broker.hivemq.com, porta 1883), porque o ESP32 simulado no Wokwi só consegue acessar brokers disponíveis na internet. Por ser público, nenhum dado pessoal trafega por MQTT: apenas identificadores técnicos, o nome do semáforo e os segundos.

## Tópicos
- fiap/gs2026/travessia/semaforo/{id}/comando: pedido de extensão enviado pelo serviço ao ESP32.
- fiap/gs2026/travessia/semaforo/{id}/confirmacao: respostas do ESP32 (ACEITO, EXECUTADO ou REJEITADO).
- fiap/gs2026/travessia/dispositivo/estado: estado do ESP32 (online, fase atual, identificador de inicialização), mensagem retida com Last Will indicando quando ele desconecta.

## Confirmação obrigatória
O backend não considera um pedido executado só porque publicou a mensagem. O ESP32 responde primeiro ACEITO e depois EXECUTADO, quando o verde de pedestres estendido realmente começa. O serviço espera o ACEITO por até 10 segundos e a execução por até 40 segundos.

## Situações de falha tratadas
- Sem resposta do ESP32: status SEM_CONFIRMACAO.
- Broker indisponível: status FALHA_MQTT.
- ESP32 desconectado: status DISPOSITIVO_OFFLINE, sem publicar o comando.
- ESP32 reiniciou durante o pedido: status DISPOSITIVO_REINICIADO.
- Pedido repetido da mesma solicitação: o mesmo comando é reaproveitado, sem publicar de novo; o ESP32 também reenvia a resposta já dada ao mesmo identificador.
- Pedidos simultâneos no mesmo semáforo: só um é processado por vez; o outro recebe SEMAFORO_OCUPADO.
- Serviço IoT fora do ar: status FALHA_COMUNICACAO_IOT.
Em todas essas situações o pedido fica registrado e o pedestre é avisado de que o tempo extra não foi aplicado.
