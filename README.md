# Lumina Signature — revisão de produção

Flask + PostgreSQL, preservando o layout aprovado e dois produtos por linha em celulares.
Não usa SQLite nem disco temporário para novas imagens. Imagens são decodificadas e
regravadas em JPEG, com cópia permanente em `uploaded_images`. Cloudinary é opcional;
se configurado, recebe uma cópia adicional. Não excluímos mídia automaticamente ao
arquivar produtos ou remover referências, para preservar restauração e histórico.

## Instalação e execução

1. Instale Python 3.12 ou superior e `pip install -r requirements.txt`.
2. Configure as variáveis descritas em `.env.example` por um canal privado.
3. **Antes de migrar produção, faça e valide um backup.**
4. Execute `python manage.py migrate`.
5. Inicie `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`.

No Render, mantenha o plano Free, build `pip install -r requirements.txt` e start:
`python manage.py migrate && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120 --access-logfile -`.
Configure health check `/readyz`. Não escreva logs de corpo de pedidos ou senhas.
O plano gratuito continua sujeito à suspensão por inatividade e às quotas do provedor.

Migrações usam versão/checksum e trava transacional. Reexecutá-las não apaga produtos,
contas, pedidos, fotos ou configurações. Dados demonstrativos não são reinseridos.
A primeira migração corrige somente categorias órfãs e acrescenta integridade; a segunda
converte valores financeiros para NUMERIC com duas casas. Faça backup antes da conversão.
Para rollback do código, volte ao commit anterior; os novos campos são compatíveis.
Rollback de dados exige **outro banco vazio**, comparação e troca controlada da conexão.

## Backup e restauração

Em ambiente com acesso PostgreSQL, `python manage.py backup /local/privado/backup.json`.
O comando usa snapshot somente leitura e consistente, inclui imagens e hashes de senha,
não inclui a connection string e cria arquivo com permissão 0600. Guarde fora do Git,
em armazenamento privado; não exponha backups no site nem em releases públicas.
Faça backup antes de cada publicação e, durante operação, diariamente; retenha pelo
menos 7 cópias diárias e 4 semanais. Essa política precisa de executor externo para ser
automática; não há rotina paga contratada nem agendamento fingido neste projeto.

`python manage.py restore /local/privado/backup.json` recusa um banco que já possui
tabelas. Configure DATABASE_URL para **destino vazio**, restaure, compare contagens,
hashes das imagens e fluxos de leitura antes de considerar trocar produção.
O JSON exportado pelo console Neon deve conter `format: lumina-backup-v1` e `tables`.
A janela de restauração do plano Neon não substitui cópias externas.

## Segurança e operação

- CSRF por sessão, verificação de origem, cookies HttpOnly/SameSite/Secure no Render.
- Senhas com hash Werkzeug; sessões revogáveis quando a versão da conta muda.
- Oito tentativas por IP/rota por 15 minutos para login/cadastro/recuperação.
- `owner` possui acesso total; `viewer` só leitura. Convites expiram em 48 horas.
- Uploads até 20 MB e 36 megapixels: JPEG/PNG/WebP/HEIF/GIF/BMP/TIFF. GIFs e TIFFs
  multipágina tornam-se a primeira imagem estática. Metadados EXIF são removidos.
- Valores e variações são validados no servidor. Idempotency-Key evita pedidos repetidos.
- Produtos são arquivados, preservando dados. Categorias possuem integridade referencial.
- Recuperação por email só fica operacional com BREVO_API_KEY, remetente verificado em MAIL_FROM e PUBLIC_BASE_URL HTTPS válidos;
  o Render gratuito bloqueia portas SMTP; sem serviço HTTPS a interface informa indisponibilidade, sem dizer que enviou email.
- Para staging protegido, use STAGING_MODE=1 e um banco independente. Não clone a URL
  do banco de produção para fazer testes de escrita.
- A interface ainda usa handlers inline; a CSP os permite. Não relaxe object-src ou
  frame-ancestors, e mantenha escape de texto e validação de mídia.

## Testes

Instale `pytest`, configure um PostgreSQL **local e isolado** em DATABASE_URL e rode
`python -m pytest -q`. O guard de testes recusa URLs que não sejam 127.0.0.1.
Os testes de restauração com dados reais exigem snapshot privado fora deste repositório.
Não execute essa suíte contra o banco de produção. A verificação da vitrine após vendas,
uploads, edição, permissões, pedidos e reinicialização deve preceder a publicação.
