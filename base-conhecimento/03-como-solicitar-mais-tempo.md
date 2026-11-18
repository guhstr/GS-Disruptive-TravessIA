# Como solicitar mais tempo de travessia

## Passo a passo
1. Faça login no aplicativo.
2. Abra a aba Travessia IA.
3. Escolha o semáforo onde você vai atravessar.
4. O aplicativo verifica a sua distância até o semáforo usando o GPS do aparelho. Em demonstrações, também é possível simular a posição com os botões "Simular Perto" e "Simular Longe".
5. Quando você estiver a até 10 metros de um semáforo ativo, o botão SOLICITAR TRAVESSIA AGORA é liberado.
6. Toque no botão e aguarde a mensagem "Aguardando confirmação do semáforo".
7. Se o sinal de pedestres estiver fechado, o tempo extra fica para a próxima abertura e o aplicativo mostra quanto falta para o sinal abrir.
8. O aplicativo mostra o resultado: se o semáforo confirmou o tempo extra, aparece "Atravesse agora" com uma contagem regressiva dos segundos que faltam para o sinal de pedestres fechar, além do clima considerado. Quando o tempo acaba, o aplicativo mostra "Travessia concluída" e o botão volta a ficar disponível para um novo pedido.

## Regras para o botão ser liberado
- O semáforo precisa estar ativo.
- O pedestre precisa estar a no máximo 10 metros do semáforo. A distância é calculada pela fórmula de Haversine com a latitude e a longitude do aparelho.
- Se o semáforo estiver inativo ou o pedestre estiver longe, o pedido é recusado pelo backend, mesmo que o aplicativo seja contornado.

## Quanto tempo a mais é concedido
O tempo padrão de travessia é de 15 segundos. Ao solicitar, o pedestre ganha 5 segundos extras em tempo seco ou 10 segundos extras quando há chuva, garoa ou tempestade. Assim, o total fica em 20 segundos (seco) ou 25 segundos (chuva).

## O que o aplicativo mostra depois do pedido
- Semáforo confirmou o tempo extra: o tempo foi aplicado.
- Semáforo aceitou: o tempo será aplicado na próxima travessia, quando o sinal de pedestres abrir.
- Semáforo recusou o pedido: por exemplo, quando a mesma travessia já recebeu tempo extra.
- Semáforo não respondeu a tempo, semáforo desconectado ou serviço indisponível: o tempo extra não foi aplicado e o pedestre deve aguardar o sinal normal.
