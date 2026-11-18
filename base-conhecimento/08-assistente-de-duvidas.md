# Assistente de dúvidas (FAQ com RAG)

## O que é
A aba Dúvidas do aplicativo tem um assistente que responde perguntas usando IA generativa com RAG (geração aumentada por recuperação). Ele responde sobre o funcionamento do Travessia Inteligente e também sobre segurança na travessia para pessoas idosas e pessoas com deficiência: dicas para atravessar, cuidados com chuva e à noite, e direitos do pedestre.

## Conversa com memória
O assistente funciona como uma conversa. Ele lembra das últimas mensagens, então é possível fazer perguntas seguidas, como "Quanto tempo a mais eu ganho?" e depois "E se estiver chovendo?". Antes de buscar na base, a IA reescreve a pergunta de acompanhamento como uma pergunta completa, usando o histórico. O botão "Nova conversa" apaga o histórico e começa do zero. O histórico fica apenas no aparelho, enquanto a tela está aberta, e não é gravado no servidor.

## Recursos de acessibilidade
Cada resposta tem o botão "Ouvir", que lê a resposta em voz alta, e o botão "Mais simples", que pede à IA a mesma explicação com frases curtas e palavras do dia a dia. Depois de cada resposta, o assistente sugere até 3 perguntas relacionadas, que a pessoa pode tocar para continuar a conversa sem precisar digitar.

## Orientação depois do pedido
Quando o semáforo confirma o tempo extra, o aplicativo mostra uma orientação curta, escrita pela IA, para a pessoa que vai atravessar. Ela informa quantos segundos a pessoa ganhou e dá dicas de segurança da base de conhecimento adequadas ao clima e ao horário, como passos curtos na chuva ou roupas claras à noite. A orientação também pode ser ouvida em voz alta. Se a IA estiver indisponível, aparece um lembrete padrão.

## Como funciona
1. A base de conhecimento do projeto é formada por documentos em Markdown.
2. Os documentos são divididos em trechos menores, respeitando as seções.
3. Cada trecho é transformado em um vetor numérico (embedding) por um modelo de embedding do Gemini.
4. Quando o usuário faz uma pergunta, ela também vira um vetor, e os trechos mais parecidos são recuperados pela similaridade de cosseno. O projeto também testou uma busca híbrida, que combina os vetores com a busca por palavras (BM25), mas ela teve resultado pior na avaliação e ficou desativada por padrão.
5. Os trechos recuperados são enviados ao modelo generativo junto com a pergunta.
6. O modelo responde usando somente esse contexto e indica as fontes usadas.

## Quando o assistente não responde
Se nenhum trecho da base for parecido o suficiente com a pergunta, ou se o contexto não tiver a informação, o assistente informa que não tem dados suficientes para responder, em vez de inventar uma resposta.

## Limitações
O assistente só conhece o conteúdo da base de conhecimento do projeto. Ele dá apenas orientações gerais de segurança, não substitui orientação médica, jurídica ou de órgãos de trânsito, não responde sobre outros assuntos e pode errar se a pergunta for ambígua.
