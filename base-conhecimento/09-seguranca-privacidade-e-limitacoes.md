# Segurança, privacidade e limitações

## Dados pessoais
O sistema armazena nome, idade, indicação de PCD e perfil do usuário, além da localização enviada no momento do pedido para calcular a distância. Esses dados não são enviados pelo MQTT nem para o assistente de IA.

## Credenciais
Senhas do banco, chaves de API e segredos ficam em arquivos .env que não são enviados ao GitHub. O repositório traz apenas arquivos .env.example sem valores reais.

## Limitações conhecidas
- O semáforo é simulado; o sistema não controla semáforos reais.
- Um único ESP32 simulado atende todos os semáforos na demonstração.
- O login é feito apenas pelo nome de usuário, sem senha.
- O broker MQTT público não tem autenticação; em um cenário real seria necessário um broker privado com TLS e usuário e senha.
- A precisão do GPS do celular pode ser maior do que 10 metros em alguns locais.
- As respostas de IA dependem da disponibilidade e da cota dos modelos Gemini; por isso existem a troca automática de modelo e textos padrão quando a IA não responde. A decisão do tempo extra não depende da IA.
