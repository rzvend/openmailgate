# G.2.5-final — Clean install validation with dashboard/OpenTofu

## Status

Aprovado com correções aplicadas.

## Ambiente validado

- VM limpa: `openmailgate2`
- IP da VM: `YOUR_VM_IP`
- Stack Docker Compose
- API/dashboard: `YOUR_VM_IP:8000`
- IMAP/Dovecot: `YOUR_VM_IP:143`
- SMTP sender: `YOUR_VM_IP:2525`

## Commits aplicados durante a validação

- `fe6b86f` — `docs: avoid inline comments in env example`
- `3f00455` — `fix: subscribe special-use IMAP folders automatically`
- `d7ec37c` — `fix: ensure Maildir ownership for Dovecot`

## Resultado validado

- `docker compose up -d --build`: OK
- API healthy: OK
- Dovecot healthy: OK
- smtp-sender healthy: OK
- worker-sqs up: OK
- Primeiro fluxo real de envio pelo Thunderbird: OK
- E-mail recebido no Gmail: OK
- Reply enviado pelo Gmail e recebido no Thunderbird: OK
- Pasta IMAP `Sent`: OK
- `doveadm mailbox list`: OK
- `doveadm mailbox status Sent`: OK
- `doveadm save -m Sent`: OK

## Problemas encontrados e corrigidos

### 1. Comentários inline no `.env.example`

O `.env.example` continha comentários inline após valores.

Isso poderia causar ambiguidade entre ferramentas como Docker Compose, `python-dotenv`, scripts shell e leitores manuais de `.env`.

Correção:

- comentários movidos para linhas separadas;
- seção duplicada `Support / About` removida;
- `.env.example` ficou mais previsível para instalação limpa.

Commit:

- `fe6b86f docs: avoid inline comments in env example`

### 2. Pastas IMAP especiais sem auto-subscribe

O Dovecot declarava pastas especiais, mas sem `auto = subscribe`.

Isso poderia dificultar a descoberta automática das pastas especiais por clientes IMAP como o Thunderbird.

Correção:

- adicionado `auto = subscribe` para:
  - `Sent`
  - `Drafts`
  - `Trash`
  - `Junk`
  - `Archive`

Commit:

- `3f00455 fix: subscribe special-use IMAP folders automatically`

### 3. Ownership incorreto do Maildir

Durante o teste, o Thunderbird enviava e-mail com sucesso, mas travava em:

> Copying message to Sent folder...

Investigação com `doveadm` mostrou erro de permissão:

> missing +w perm: /app/data/maildir/ricardo, dir owned by 0:0 mode=0755

Causa:

- Maildir criado como `root:root`;
- Dovecot roda como UID/GID `1000:1000`;
- Dovecot não conseguia criar índices, `uidlist` nem salvar mensagens em `Sent`;
- o problema afetava operações IMAP como listagem, status e `APPEND` em pastas da mailbox.

Correção:

- `worker/mailbox_admin.py` passou a usar `database.ensure_maildir_structure()`;
- `docker-entrypoint.py` passou a normalizar ownership do Maildir no startup;
- mailboxes existentes passaram a ser corrigidas para o UID/GID usado pelo Dovecot.

Commit:

- `d7ec37c fix: ensure Maildir ownership for Dovecot`

## Teste final

Após as correções:

- e-mail enviado pelo Thunderbird chegou ao Gmail;
- reply enviado pelo Gmail chegou ao Thunderbird;
- `Sent` aceitou gravação;
- `doveadm mailbox list` funcionou sem `Permission denied`;
- `doveadm mailbox status Sent` funcionou;
- `doveadm save -m Sent` incrementou a contagem de mensagens;
- serviços principais permaneceram saudáveis;
- não houve novos erros relevantes nos logs finais.

## Fluxo real validado

A etapa validou o fluxo real de envio:

- Thunderbird → SMTP sender → SES → Gmail

E também o fluxo real de recebimento/reply:

- Gmail reply → SES/S3/SQS/worker → Maildir/Dovecot → Thunderbird

## Estado final dos serviços

Estado observado ao final da validação:

- API: healthy
- Dovecot: healthy
- smtp-sender: healthy
- worker-sqs: up

## Pendências observadas

### 1. Warning do Docker Compose

O Docker Compose ainda mostra o aviso:

> the attribute `version` is obsolete

Isso não bloqueia a execução, mas deve ser removido para deixar a instalação alpha mais limpa.

Sugestão de commit futuro:

- `chore: remove obsolete compose version field`

### 2. Segunda validação limpa recomendada

Como bugs foram corrigidos durante a validação, recomenda-se executar uma nova validação em VM limpa ou ambiente limpo após os commits:

- `fe6b86f`
- `3f00455`
- `d7ec37c`

Sugestão de próxima etapa:

- `G.2.6 — Clean reinstall after fixes`

Objetivo:

- validar que uma instalação limpa já nasce funcional sem correções manuais intermediárias.

## Conclusão

A etapa `G.2.5-final` validou que a stack em VM limpa consegue operar envio e recebimento reais de e-mail usando Thunderbird, SES, S3, SQS, worker, Maildir e Dovecot.

Status: aprovado com correções aplicadas.
