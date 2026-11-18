# Semáforo simulado (ESP32 no Wokwi)

## Hardware simulado
O semáforo é simulado em um ESP32 no Wokwi com:
- três LEDs para veículos (vermelho, amarelo e verde);
- dois LEDs para pedestres (vermelho e verde);
- um display LCD 16x2 com a contagem regressiva (em quanto tempo o sinal de pedestres abre ou quanto tempo resta para atravessar, e o mesmo para os veículos);
- um segundo display LCD 16x2 que mostra o número e o nome do semáforo atendido e se o ESP32 está conectado ao broker MQTT (ON ou OFF).

## Ciclo de fases
1. Todos vermelhos: 2 segundos.
2. Veículos verde: 10 segundos.
3. Veículos amarelo: 3 segundos.
4. Todos vermelhos: 2 segundos.
5. Pedestres verde: 11 segundos, mais o tempo extra quando houver.
6. Pedestres verde piscando: 4 segundos.
O tempo padrão de travessia é de 15 segundos (11 de verde fixo e 4 piscando).

## Regras de segurança
- Os sinais de veículos e de pedestres nunca ficam verdes ao mesmo tempo. Se isso fosse solicitado, o firmware força todos os sinais para vermelho.
- O tempo extra nunca interrompe nem encurta o verde dos veículos. Se o pedido chega durante a travessia de pedestres, o verde é estendido na hora. Se chega com o sinal de pedestres fechado, o tempo extra fica agendado para a próxima travessia.
- Cada travessia aceita apenas uma extensão. Um segundo pedido na mesma travessia é recusado.
- O ESP32 aceita no máximo 15 segundos extras por comando e rejeita comandos inválidos.
- Ao ligar ou reiniciar, o ESP32 começa com todos os sinais vermelhos.
- Se perder a conexão Wi-Fi ou MQTT, o semáforo continua o ciclo normal, que é seguro, e apenas deixa de aceitar pedidos de tempo extra.

## Um controlador para vários semáforos
Na simulação, um único ESP32 atende qualquer semáforo cadastrado no sistema: o número do semáforo vem no tópico MQTT e o nome vem no comando. O segundo LCD mostra qual semáforo fez o último pedido.

## Log serial
O monitor serial do Wokwi registra cada mudança de fase e cada pedido feito pelo aplicativo, por exemplo quando o pedestre pede mais tempo, quando o tempo é agendado, aplicado ou recusado.
