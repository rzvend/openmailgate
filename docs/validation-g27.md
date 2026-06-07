# G.2.7 — Final clean install release candidate

Status: aprovado

Data: 2026-06-07

## Objetivo

Executar uma instalação realmente limpa do OpenMailGate após as correções aprovadas na G.2.6, confirmando que o projeto consegue ser instalado do zero sem commits, patches ou workarounds durante o processo.

O objetivo principal era validar se os dois bloqueadores identificados na G.2.6 estavam definitivamente corrigidos:

1. falha no primeiro apply do SES Custom MAIL FROM;
2. ownership incorreto do Maildir da primeira mailbox criada pelo dashboard.

## Domínio validado

```text
boto.ricardo.vc
```

Custom MAIL FROM esperado:

```text
mail.boto.ricardo.vc
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

## Commits presentes desde o início

A instalação limpa foi iniciada já com os commits finais presentes:

```text
f595f3d fix: ensure Maildir subfolder ownership for Dovecot
ee557b1 fix: wait for SES identity before custom MAIL FROM
16a3ccb feat: add SES custom MAIL FROM automation
2cc2343 docs: sanitize README examples
4d8b1ae chore: remove obsolete compose version field
60b4e8d docs: record clean install validation results
```

O repositório estava limpo:

```text
nothing to commit, working tree clean
```

## Preparação

Foi criado um novo `.env` a partir do `.env.example`:

```bash
cp .env.example .env
```

O domínio configurado foi:

```text
MAIL_DOMAIN=boto.ricardo.vc
```

Os binds foram configurados para a VM:

```text
API_BIND=10.10.10.56
IMAP_BIND=10.10.10.56
SMTP_BIND=10.10.10.56
```

No início, os campos abaixo permaneceram como placeholders ou vazios, conforme esperado:

```text
S3_BUCKET=
SQS_QUEUE_URL=CHANGE_ME
SES_SMTP_USERNAME=CHANGE_ME
SES_SMTP_PASSWORD=CHANGE_ME
```

Esses valores deveriam ser criados pelo OpenTofu e sincronizados pelo dashboard.

## Docker Compose config

O comando:

```bash
docker compose config
```

foi executado com sucesso.

Pontos validados:

```text
MAIL_DOMAIN=boto.ricardo.vc
API_BIND=10.10.10.56
IMAP_BIND=10.10.10.56
SMTP_BIND=10.10.10.56
Sem warning de version obsoleto
Sem erro de renderização do Compose
```

Durante a preparação da VM houve um problema de permissão do usuário no Docker:

```text
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
```

Classificação:

```text
Problema de ambiente da VM, não bug do OpenMailGate.
```

Correção esperada:

```bash
sudo usermod -aG docker "$USER"
```

e reabrir a sessão, ou usar `newgrp docker`.

## OpenTofu plan

O dashboard executou o OpenTofu `plan` com sucesso.

Resultado:

```text
Plan: 23 to add, 0 to change, 0 to destroy.
```

Essa contagem era esperada após a correção `ee557b1`, pois o plano passou a incluir:

```text
time_sleep.wait_ses_identity
```

Recursos planejados:

* IAM user para SMTP
* IAM access key para SMTP
* IAM policy para envio via SES
* S3 bucket
* S3 bucket policy
* S3 public access block
* S3 notification para SQS
* SQS queue
* SQS queue policy
* SES domain identity
* SES DKIM
* SES Custom MAIL FROM
* SES receipt rule set
* SES active receipt rule set
* SES receipt rule para S3
* Cloudflare MX do domínio
* Cloudflare TXT SPF do MAIL FROM
* Cloudflare MX do MAIL FROM
* Cloudflare TXT de verificação SES
* Cloudflare DKIM CNAMEs
* `time_sleep.wait_ses_identity`

Domínio planejado:

```text
boto.ricardo.vc
```

Custom MAIL FROM planejado:

```text
mail.boto.ricardo.vc
```

Bucket planejado:

```text
ses-openmailgate-88d29e9a-mailbox
```

Fila planejada:

```text
ses-openmailgate-88d29e9a-incoming
```

Regra SES planejada:

```text
store-in-s3-88d29e9a
```

Rule set planejado:

```text
ses-s3-mailbox-88d29e9a-rules
```

## Validação do bug G.2.6a

A etapa G.2.7 validou que o bug anterior do SES Custom MAIL FROM não reapareceu.

Antes da correção, o primeiro apply podia falhar com:

```text
InvalidParameterValue: Identity does not exist
```

Na instalação limpa final, o plano incluiu corretamente:

```text
time_sleep.wait_ses_identity
```

e o recurso:

```text
aws_ses_domain_mail_from.this
```

foi planejado para:

```text
domain = "boto.ricardo.vc"
mail_from_domain = "mail.boto.ricardo.vc"
```

Resultado:

```text
G.2.6a validado em instalação limpa final.
```

## Runtime env sync

Após o apply, os outputs esperados foram sincronizados para o `.env` pelo dashboard.

Chaves esperadas:

```text
DEFAULT_FROM_DOMAIN
S3_BUCKET
SQS_QUEUE_URL
SES_SMTP_USERNAME
SES_SMTP_PASSWORD
```

Foi necessário recriar os serviços dependentes de `env_file`, conforme comportamento normal do Docker Compose:

```bash
docker compose up -d --force-recreate api worker-sqs smtp-sender
```

Classificação:

```text
Comportamento esperado/documentável.
```

## Post-apply validation

A validação pós-apply confirmou os recursos principais.

Itens esperados:

* SES identity
* SES DKIM
* SES MAIL FROM
* DNS MAIL FROM MX
* DNS MAIL FROM SPF
* S3 bucket
* S3 notification
* SQS queue
* SES receipt rule
* Cloudflare DNS

Resultado geral:

```text
Post-apply validation: OK
```

## Criação de mailbox

Foi criada uma mailbox pelo dashboard.

Resultado:

```text
Mailbox criada com sucesso.
```

A etapa validou o fluxo:

```text
Dashboard → criação de mailbox → sync Dovecot users → Dovecot restart → Thunderbird
```

## Validação do bug G.2.6b

A G.2.7 validou que o bug de ownership do Maildir não reapareceu em instalação limpa.

Antes da correção, a primeira mailbox criada pelo dashboard podia gerar diretórios como:

```text
/app/data/maildir/<mailbox> root:root
/app/data/maildir/<mailbox>/.Sent root:root
```

causando erro no Dovecot:

```text
Permission denied
```

Depois do commit:

```text
f595f3d fix: ensure Maildir subfolder ownership for Dovecot
```

a mailbox criada pelo dashboard funcionou sem `chown` manual.

Resultado:

```text
G.2.6b validado em instalação limpa final.
```

## Teste real de envio

Foi configurado Thunderbird com:

```text
IMAP: 10.10.10.56:143
SMTP: 10.10.10.56:2525
```

O envio real foi realizado com sucesso.

Fluxo validado:

```text
Thunderbird → smtp-sender → Amazon SES → destinatário externo
```

Resultado:

```text
Envio: OK
```

A mensagem enviada foi salva corretamente na pasta de saída/Sent.

Resultado:

```text
Sent: OK
```

## Teste real de recebimento/reply

Foi respondido o e-mail a partir do destinatário externo.

Fluxo validado:

```text
destinatário externo → Amazon SES → S3 → SQS → worker-sqs → Maildir → Dovecot → Thunderbird
```

Resultado:

```text
Reply recebido: OK
```

O e-mail recebido foi salvo corretamente na entrada.

Resultado:

```text
Entrada: OK
```

## Resultado final

A instalação limpa final foi aprovada.

Checklist validado:

```text
VM limpa: OK
Repositório atualizado: OK
Commits ee557b1/f595f3d presentes: OK
Working tree limpo: OK
.env criado a partir do .env.example: OK
docker compose config: OK
docker compose up -d --build: OK
Dashboard: OK
First admin: OK
AWS credentials validation: OK
Cloudflare credentials validation: OK
IAM preflight: OK
OpenTofu init: OK
OpenTofu plan: OK
Plan 23 add / 0 change / 0 destroy: OK
OpenTofu apply: OK
SES Custom MAIL FROM no primeiro apply: OK
Runtime env sync: OK
Serviços recriados com novo env_file: OK
Post-apply validation: OK
Mailbox criada pelo dashboard: OK
Dovecot/IMAP: OK
Maildir ownership sem chown manual: OK
Thunderbird envia: OK
Thunderbird salva Sent: OK
Reply recebido: OK
Entrada salva: OK
Saída salva: OK
Nenhum commit durante o teste: OK
Nenhum workaround manual no OpenMailGate: OK
```

## Classificação

```text
G.2.7 — Final clean install release candidate
Status: aprovado
```

## Conclusão

A instalação limpa final confirmou que o OpenMailGate pode ser instalado do zero em uma VM limpa, usando o fluxo atual de Docker Compose, dashboard e OpenTofu, sem commits ou patches durante a instalação.

Os dois bloqueadores identificados na G.2.6 foram validados como corrigidos:

```text
G.2.6a — SES Custom MAIL FROM apply timing: corrigido
G.2.6b — Maildir ownership for dashboard-created mailboxes: corrigido
```

A partir desta validação, o projeto pode avançar para os passos finais antes da release:

1. revisar README/deploy alpha;
2. incluir About/licença/créditos no dashboard;
3. criar checklist de segurança alpha;
4. agrupar falhas pré-existentes de testes por causa raiz;
5. preparar release notes;
6. criar tag `v0.1.0-alpha`.
