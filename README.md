# ObraFácil — gestão para material de construção

Aplicação web local em Python/Flask, SQLite, HTML, CSS e JavaScript.

## Recursos

- Login e controle de acesso para administradores e vendedores.
- CRUD de produtos: cadastro, consulta, pesquisa, edição e exclusão.
- Cadastro e edição de usuários da equipe; ativação e desativação de contas.
- Registro de vendas com vários produtos, formas de pagamento e baixa automática de estoque.
- Painel com faturamento e vendas do dia, vendas recentes e alertas de estoque mínimo.
- Proteção CSRF em formulários e senhas armazenadas com hash.

## Executar

Requer Python 3.10 ou superior.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = "troque-por-uma-chave-secreta-forte"
python app.py
```

Abra http://127.0.0.1:5000 no navegador.

No primeiro início, o banco `loja.db` é criado automaticamente junto com o usuário administrador:

- E-mail: `admin@loja.local`
- Senha: `admin123`

Altere a senha após entrar em **Minha conta**. Senhas alteradas precisam ter pelo menos 12 caracteres.

## Publicar no Render

O arquivo `render.yaml` prepara um serviço web com Gunicorn, chave de sessão gerada pelo Render, senha inicial gerada e disco persistente para o SQLite. O disco persistente requer uma instância paga do Render.

1. Conecte este repositório ao Render. Este repositório está público: o código ficará visível, mas o banco de dados e os arquivos de ambiente são excluídos pelo `.gitignore`.
2. No Render, selecione **New → Blueprint**, conecte o repositório e confirme a configuração descrita em `render.yaml`.
3. Quando o serviço estiver pronto, consulte a variável `INITIAL_ADMIN_PASSWORD` em **Environment** no painel do serviço. Entre em `admin@loja.local` com essa senha gerada e troque-a em **Minha conta**.
4. Compartilhe o endereço HTTPS do serviço apenas com as pessoas que devem acessar a loja.

O Render hospeda a aplicação publicamente, mas o acesso ao sistema continua protegido por login. Nunca publique o banco de dados nem compartilhe as variáveis secretas. O endereço público só será criado depois de conectar sua conta Render ao repositório e concluir o deploy.
