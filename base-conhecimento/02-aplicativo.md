# Funcionamento do aplicativo

## Plataforma
O aplicativo foi desenvolvido em React Native com Expo e TypeScript e roda em Android, iOS e pelo Expo Go.

## Cadastro e login
- No cadastro, o usuário informa nome, idade, se é PCD e o perfil. O cadastro só é aceito para pessoas com 60 anos ou mais ou PCD.
- O login é feito pelo nome de usuário cadastrado. Após o login, o aplicativo guarda um token JWT válido por 1 ano, então a sessão continua ativa até o usuário fazer logout.
- Existem dois perfis: USUARIO (cidadão) e ADMIN (gestor).

## Telas
- Semáforos: lista os semáforos cadastrados, com descrição, coordenadas e situação (ativo ou inativo). O administrador também pode cadastrar, editar, ativar, desativar e excluir semáforos.
- Travessia IA: tela onde o pedestre escolhe o semáforo, verifica a proximidade e pede mais tempo de travessia.
- Histórico: mostra as solicitações já feitas, com data, segundos extras, clima e a resposta do semáforo. Para o administrador, mostra também um resumo com IA dos últimos 7, 30 ou 90 dias, com indicadores (total de pedidos, percentual com chuva, semáforos mais usados, falhas) e recomendações para a prefeitura. O resumo usa apenas números agregados, sem dados pessoais.
- Meu Perfil: permite editar os dados do usuário e fazer logout. O administrador também gerencia usuários.
- Dúvidas: conversa com o assistente de IA, que responde sobre o aplicativo e sobre segurança na travessia com base na base de conhecimento do projeto.

## Permissões
Somente o perfil ADMIN pode cadastrar, alterar ou remover semáforos. Usuários comuns podem consultar semáforos, verificar a proximidade e solicitar tempo extra.
