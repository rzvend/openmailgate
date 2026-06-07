# G.2.6 — Clean Reinstall after bug fixes

Status: aprovado com correções durante a validação

Data: 2026-06-07

## Objetivo

Validar uma instalação limpa do OpenMailGate após as correções anteriores do fluxo Docker/dashboard/OpenTofu, usando o domínio:

```text
alpha.example.com
```

O objetivo era confirmar se o projeto já conseguia sair de uma VM limpa até um ciclo real de envio e recebimento de e-mail, usando:

```text
Thunderbird → smtp-sender → Amazon SES → destinatário externo
destinatário externo → Amazon SES → S3 → SQS → worker-sqs → Maildir → Dovecot → Thunderbird
```

## Ambiente

* VM limpa
* Docker Compose
* Dashboard web
* OpenTofu executado pelo dashboard
* AWS SES/S3/SQS
* Cloudflare DNS
* Dovecot IMAP
* smtp-sender local
* Thunderbird como cliente IMAP/SMTP

## Commits presentes no início da validação

Entre os commits presentes no início do teste estavam:

```text
16a3ccb feat: add SES custom MAIL FROM automation
2cc2343 docs: sanitize README examples
4d8b1ae chore: remove obsolete compose version field
60b4e8d docs: record clean install validation results
```

Durante a validação, dois bloqueadores foram identificados e corrigidos.

## Fluxo validado antes das correções

A instalação inicial avançou corretamente até o OpenTofu:

* `docker compose config` executado com sucesso
* stack Docker subiu
* dashboard abriu
* primeiro administrador criado
* login funcionando
* credenciais AWS/Cloudflare validadas
* IAM preflight aprovado
* OpenTofu `init` aprovado
* OpenTofu `plan` aprovado

O primeiro `plan` mostrou:

```text
Plan: 22 to add, 0 to change, 0 to destroy.
```

O domínio estava correto:

```text
alpha.example.com
```

Os recursos planejados incluíam:

* SES domain identity
* SES DKIM
* SES Custom MAIL FROM
* SES receipt rule set
* SES receipt rule
* S3 bucket
* S3 notification
* SQS queue
* SQS policy
* IAM user/policy/access key para SMTP
* Cloudflare MX
* Cloudflare SPF
* Cloudflare DKIM
* Cloudflare SES verification
* Cloudflare MAIL FROM MX
* Cloudflare MAIL FROM SPF

## Problema 1 — SES Custom MAIL FROM timing

Durante o primeiro `apply`, quase todos os recursos foram criados, mas o recurso `aws_ses_domain_mail_from.this` falhou com erro semelhante a:

```text
InvalidParameterValue: Identity does not exist.
```

A identidade SES havia sido criada segundos antes:

```text
aws_ses_domain_identity.domain: Creation complete
```

Depois de um novo `plan`, restava apenas:

```text
Plan: 1 to add, 0 to change, 0 to destroy.
```

O recurso pendente era:

```text
aws_ses_domain_mail_from.this
```

### Diagnóstico

O recurso `aws_ses_domain_mail_from.this` tentava configurar o Custom MAIL FROM imediatamente após criar a domain identity do SES.

O problema era uma combinação de:

* ausência de dependência explícita robusta;
* uso de `var.domain` em vez de referência direta ao recurso `aws_ses_domain_identity.domain`;
* propagação eventual do SES logo após a criação da identity.

### Correção aplicada

Commit:

```text
ee557b1 fix: wait for SES identity before custom MAIL FROM
```

Correção:

* adicionado provider `hashicorp/time`;
* adicionado `time_sleep.wait_ses_identity`;
* `aws_ses_domain_mail_from.this` passou a usar `aws_ses_domain_identity.domain.domain`;
* `aws_ses_domain_mail_from.this` passou a depender de `time_sleep.wait_ses_identity`.

Depois da correção, o apply pendente passou:

```text
time_sleep.wait_ses_identity: Creation complete after 20s
aws_ses_domain_mail_from.this: Creation complete
Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```

### Resultado

O Custom MAIL FROM foi validado:

```text
custom_mail_from_domain = "mail.alpha.example.com"
```

A validação pós-apply mostrou:

```text
SES | MAIL FROM | ok | mail.alpha.example.com
DNS | MAIL FROM MX | ok | found
DNS | MAIL FROM SPF | ok | found
```

## Runtime env sync

Após o apply, o dashboard sincronizou os outputs do OpenTofu para o `.env`.

Chaves atualizadas:

```text
DEFAULT_FROM_DOMAIN
S3_BUCKET
SES_SMTP_PASSWORD
SES_SMTP_USERNAME
SQS_QUEUE_URL
```

Resultado:

```text
Runtime env sync: OK
```

Foi necessário recriar os serviços para aplicar os valores do `env_file`, conforme orientação do próprio dashboard:

```bash
docker compose up -d --force-recreate api worker-sqs smtp-sender
```

Classificação:

```text
Não bloqueia alpha, mas deve estar documentado.
```

## Post-apply validation

Após a correção e sincronização, a validação pós-apply passou:

```text
OK: 13
Warning: 0
Error: 0
Skipped: 1
```

Itens principais validados:

* AWS STS
* S3 bucket
* SQS queue
* S3 notification
* SES identity
* SES DKIM
* SES receipt rule set
* SES receipt rule
* SES MAIL FROM
* Cloudflare zone
* DNS MX
* DNS SPF
* DNS DKIM
* DNS MAIL FROM MX
* DNS MAIL FROM SPF

O item `OpenTofu Outputs` apareceu como `skipped` em uma validação, apesar de os outputs terem sido sincronizados corretamente para o `.env`.

Classificação:

```text
Não bloqueia alpha, mas deve documentar/refinar posteriormente.
```

## Problema 2 — Maildir ownership em mailbox criada pelo dashboard

Após criar a primeira mailbox pelo dashboard:

```text
user@alpha.example.com
```

o dashboard escreveu o usuário em:

```text
/app/dovecot/users
```

e orientou reiniciar o Dovecot.

O Thunderbird conseguiu enviar a mensagem, mas falhou ao salvar a cópia na pasta `Sent`.

Mensagem observada:

```text
Your message was sent but a copy was not placed in your sent folder (Sent) due to network or file access errors.
```

O Dovecot mostrava o usuário com:

```text
uid 1000
gid 1000
mail maildir:/app/data/maildir/ricardo
```

Mas o Maildir e as pastas intermediárias estavam com owner incorreto:

```text
root:root
```

Erros típicos:

```text
file_dotlock_open(/app/data/maildir/ricardo/dovecot.list.index.log) failed: Permission denied
missing +w perm: /app/data/maildir/ricardo, dir owned by 0:0 mode=0755
```

E também:

```text
Mailbox Sent: file_dotlock_open(/app/data/maildir/ricardo/.Sent/dovecot.index.log) failed: Permission denied
missing +w perm: /app/data/maildir/ricardo/.Sent, dir owned by 0:0 mode=0755
```

### Histórico de recorrência

Esse problema já havia ocorrido em validações anteriores de instalação limpa.

As correções anteriores resolveram parcialmente ou provisoriamente o problema, especialmente quando o ownership era normalizado no startup ou por workaround manual.

A recorrência mostrou que o problema real estava na função central de criação da estrutura Maildir.

### Diagnóstico

A função `ensure_maildir_structure()` criava os diretórios finais como:

```text
.Sent/cur
.Sent/new
.Sent/tmp
```

mas não aplicava ownership aos diretórios intermediários:

```text
.Sent
.Drafts
.Trash
.Junk
.Archive
.SentDuplicates
```

Também era necessário garantir ownership da própria raiz da mailbox:

```text
/app/data/maildir/<mailbox>
```

O Dovecot precisa escrever arquivos como:

```text
dovecot.index.log
dovecot-uidlist
dovecot-uidvalidity.*
```

na raiz da mailbox e nos diretórios intermediários das pastas especiais.

### Correção aplicada

Commit:

```text
f595f3d fix: ensure Maildir subfolder ownership for Dovecot
```

Correção em `database.py`:

* adicionada a raiz da mailbox ao loop de ownership;
* adicionados os diretórios intermediários das pastas especiais ao loop de ownership.

Entradas adicionadas:

```text
""
".Sent"
".Drafts"
".Trash"
".Junk"
".Archive"
".SentDuplicates"
```

Resultado esperado:

```text
/app/data/maildir/<mailbox>                    uid=1000 gid=1000
/app/data/maildir/<mailbox>/.Sent              uid=1000 gid=1000
/app/data/maildir/<mailbox>/.Drafts            uid=1000 gid=1000
/app/data/maildir/<mailbox>/.Trash             uid=1000 gid=1000
/app/data/maildir/<mailbox>/.Junk              uid=1000 gid=1000
/app/data/maildir/<mailbox>/.Archive           uid=1000 gid=1000
/app/data/maildir/<mailbox>/.SentDuplicates    uid=1000 gid=1000
```

### Validação da correção

Após a correção:

```text
ALL OWNERSHIPS 1000:1000
compileall: OK
pytest: 71 pass, 56 fail pré-existentes
```

O teste de envio e recebimento foi repetido.

Resultado:

* envio pelo Thunderbird funcionou;
* e-mail foi salvo corretamente em `Sent`;
* reply externo foi recebido;
* e-mail recebido foi salvo corretamente na entrada;
* não foi necessário `chown` manual após a correção.

## Resultado final da G.2.6

A etapa foi aprovada com correções durante a validação.

Resultado final:

```text
Clean install: OK
Dashboard setup: OK
OpenTofu init: OK
OpenTofu plan: OK
OpenTofu apply: OK após correção
SES Custom MAIL FROM: OK
Post-apply validation: OK
Runtime env sync: OK
First mailbox: OK
Dovecot IMAP: OK
smtp-sender: OK
Thunderbird envia: OK
Thunderbird salva Sent: OK
Reply externo recebido: OK
Entrada salva: OK
Saída salva: OK
```

## Correções aprovadas nesta etapa

### G.2.6a — Fix SES Custom MAIL FROM apply timing

Status: aprovado

Commit:

```text
ee557b1 fix: wait for SES identity before custom MAIL FROM
```

Classificação:

```text
Bloqueador de instalação limpa corrigido.
```

### G.2.6b — Fix Maildir ownership for dashboard-created mailboxes

Status: aprovado

Commit:

```text
f595f3d fix: ensure Maildir subfolder ownership for Dovecot
```

Classificação:

```text
Bloqueador alpha corrigido.
```

## Lacunas observadas

### Não bloqueia alpha, mas deve documentar

* Após Runtime Env Sync, é necessário recriar os serviços que dependem de `env_file`:

```bash
docker compose up -d --force-recreate api worker-sqs smtp-sender
```

* O check de OpenTofu outputs pode aparecer como `skipped` em determinada situação, mesmo com os outputs já sincronizados para o `.env`.

### Melhoria pós-alpha

* Melhorar UX do dashboard para deixar o botão de validação pós-apply mais evidente.
* Documentar melhor o fluxo de recriação de containers após sync do `.env`.
* Investigar e agrupar as falhas pré-existentes dos testes automatizados.
* Evoluir para TLS/HTTPS/IMAPS/SMTP seguro em etapa de produção.

## Conclusão

A G.2.6 cumpriu seu papel de encontrar e corrigir dois bloqueadores reais do fluxo de instalação limpa:

1. timing do SES Custom MAIL FROM;
2. ownership incorreto do Maildir na primeira mailbox criada pelo dashboard.

Após as correções, o fluxo de envio, salvamento em `Sent`, recebimento de reply e salvamento de entrada foi validado com sucesso.

A etapa seguinte recomendada é uma instalação realmente limpa final, já com os commits `ee557b1` e `f595f3d` presentes desde o início, sem commits ou patches durante o processo.
