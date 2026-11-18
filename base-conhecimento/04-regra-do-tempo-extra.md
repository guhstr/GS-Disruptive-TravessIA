# Regra do tempo extra e uso do clima

## Consulta do clima
Quando o pedido é feito, o backend consulta o clima atual na coordenada do semáforo usando a API OpenWeatherMap, em português. Se a chave do OpenWeatherMap não estiver configurada ou a consulta falhar, o sistema considera "Céu limpo".

## Como o tempo extra é decidido
A decisão usa o código numérico da condição do clima que o OpenWeatherMap devolve, e não o texto. Se o código indica tempestade (2xx), garoa (3xx), chuva (5xx) ou neve (6xx), a pessoa ganha 10 segundos extras. Nos demais casos, como céu limpo, nuvens ou névoa, ganha 5 segundos extras. Por exemplo: "Trovoada com chuva fraca" e "Garoa fraca" dão 10 segundos; "Céu limpo" e "Nublado" dão 5 segundos.

## Por que é uma regra fixa e não IA
A pergunta é simples (está chovendo ou não) e precisa ter sempre a mesma resposta. Por isso o projeto usa uma regra fixa: é instantânea, não depende de internet nem de cota de IA e sempre dá o mesmo resultado para o mesmo clima. A IA generativa é usada onde ela agrega mais: no assistente de dúvidas, na orientação depois do pedido e no resumo para o gestor.
