# SES S3 Mailbox

Recebimento, armazenamento e leitura de e-mails usando Amazon SES, S3, SQS e Dovecot.

## Arquitetura

```
Amazon SES Receiving
    ↓
S3 bucket (ricardo-vc-ses-mailbox)
    ↓
S3 Event Notification → SQS queue
    ↓
sqs_worker.py (long polling)  ←── produção
worker.py (polling S3)        ←── fallback / manual
    ↓
data/raw-emails/ + data/maildir/master/
    ↓
SQLite (data/mailbox.db)
    ↓
Dovecot IMAP
    ↓
Thunderbird
```

## Estrutura do projeto

```
ses-s3-mailbox/
├── .env.example          # template de configuração
├── .env                  # configuração real (não versionado)
├── requirements.txt
├── README.md
├── scripts/
│   ├── setup_sqs_s3_notifications.sh       # configura SQS policy + S3 notification
│   ├── install_sqs_worker_systemd.sh       # instala serviço SQS
│   └── install_smtp_sender_systemd.sh      # instala serviço SMTP sender
├── systemd/
│   ├── ses-s3-mailbox-sqs-worker.service
│   └── ses-s3-mailbox-smtp-sender.service
├── sender/
│   ├── __init__.py
│   ├── config.py          # configuração SMTP/SES
│   ├── smtp_server.py     # servidor SMTP local (aiosmtpd)
│   ├── ses_relay.py       # relay via SES SMTP (smtplib)
│   └── store.py           # Maildir .Sent + SQLite outbound
├── worker/
│   ├── __init__.py
│   ├── worker.py          # modo polling S3 (fallback)
│   ├── sqs_worker.py      # daemon SQS long polling (produção)
│   └── migrate.py         # migração do SQLite
├── data/
│   ├── mailbox.db         # SQLite (não versionado)
│   ├── raw-emails/        # e-mails inbound brutos (não versionado)
│   ├── raw-outbound/      # e-mails outbound brutos (não versionado)
│   └── maildir/           # Maildir do Dovecot (não versionado)
└── terraform/             # infraestrutura AWS
```

## Pré-requisitos

- Python 3.11+
- boto3, python-dotenv, aiosmtpd (`pip install -r requirements.txt`)
- AWS credentials configuradas (`aws configure` ou IAM Role)
- Dovecot instalado e apontando para `data/maildir/master/`

### Permissões IAM necessárias

**S3** (bucket `ricardo-vc-ses-mailbox`):
- `s3:ListBucket`
- `s3:GetObject`
- `s3:PutObject`
- `s3:DeleteObject`

**SQS** (fila `ses-s3-mailbox-incoming`):
- `sqs:ReceiveMessage`
- `sqs:DeleteMessage`
- `sqs:GetQueueAttributes`
- `sqs:ChangeMessageVisibility`

**SES** (envio outbound):
- `ses:SendRawEmail`

## Configuração

Copie o template e ajuste:

```bash
cp .env.example .env
vim .env
```

Variáveis:

| Variável | Descrição | Padrão |
|---|---|---|
| `AWS_REGION` | Região AWS | `us-east-1` |
| `S3_BUCKET` | Nome do bucket S3 | `ricardo-vc-ses-mailbox` |
| `S3_INCOMING_PREFIX` | Prefixo de entrada | `incoming/` |
| `S3_PROCESSED_PREFIX` | Prefixo de processados | `processed/` |
| `S3_FAILED_PREFIX` | Prefixo de falhas | `failed/` |
| `BASE_DIR` | Diretório base do projeto | `~/ses-s3-mailbox` |
| `MASTER_MAILDIR` | Maildir master do Dovecot | `…/data/maildir/master` |
| `DB_PATH` | Caminho do SQLite | `…/data/mailbox.db` |
| `SQS_QUEUE_URL` | URL da fila SQS | — |
| `SQS_WAIT_TIME_SECONDS` | Long polling timeout | `20` |
| `SQS_MAX_MESSAGES` | Máximo de mensagens por lote | `10` |

## Infraestrutura AWS

### Setup automatizado

```bash
bash scripts/setup_sqs_s3_notifications.sh
```

Este script configura:
1. SQS Queue Policy — permite S3 enviar mensagens para a fila
2. S3 Event Notification — eventos `ObjectCreated:*` no prefixo `incoming/` → SQS
3. Backup da configuração existente antes de aplicar

### Manual (referência)

**SQS Queue:**
```bash
aws sqs create-queue \
  --queue-name ses-s3-mailbox-incoming \
  --region us-east-1
```

**S3 Event Notification (com filtro incoming/):**
```bash
aws s3api put-bucket-notification-configuration \
  --bucket ricardo-vc-ses-mailbox \
  --notification-configuration '{
    "QueueConfigurations": [{
      "QueueArn": "arn:aws:sqs:us-east-1:ACCOUNT_ID:ses-s3-mailbox-incoming",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {"FilterRules": [{"Name": "prefix", "Value": "incoming/"}]}
      }
    }]
  }'
```

> O filtro `incoming/` é essencial para evitar loops de eventos quando o worker move objetos para `processed/` ou `failed/`.

## SQS event mode

Configuração e operação do worker SQS.

### 1. Configurar .env

```env
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/121234001765/ses-s3-mailbox-incoming
SQS_WAIT_TIME_SECONDS=20
SQS_MAX_MESSAGES=10
```

### 2. Criar/verificar fila SQS

```bash
aws sqs get-queue-url --queue-name ses-s3-mailbox-incoming --region us-east-1
```

### 3. Configurar SQS + S3 notification

```bash
bash scripts/setup_sqs_s3_notifications.sh
```

### 4. Rodar worker SQS manualmente

```bash
python3 -m worker.sqs_worker
```

### 5. Instalar como serviço systemd

```bash
bash scripts/install_sqs_worker_systemd.sh
```

### 6. Acompanhar logs

```bash
journalctl -u ses-s3-mailbox-sqs-worker -f
```

### 7. Testar com e-mail real

Enviar e-mail para `teste@inbox.ricardo.vc`.

Resultado esperado no log:
```
[INFO] Received 1 message(s)
[INFO] Processing incoming/<id> (event: ObjectCreated:Put)
[INFO] Downloading: incoming/<id> (NNNN bytes)
[INFO] OK  incoming/<id>
[INFO] Moved s3://ricardo-vc-ses-mailbox/incoming/<id> → processed/<id>
```

### 8. Verificar bucket S3

```bash
aws s3 ls s3://ricardo-vc-ses-mailbox/incoming/ --recursive
aws s3 ls s3://ricardo-vc-ses-mailbox/processed/ --recursive
aws s3 ls s3://ricardo-vc-ses-mailbox/failed/ --recursive
```

Esperado: `incoming/` vazio, `processed/` com o novo objeto, `failed/` vazio.

### 9. Timer antigo (fallback)

O timer `ses-s3-mailbox-worker.timer` continua ativo como fallback durante a validação do SQS. Ambos podem coexistir — o SQS processa primeiro via evento, e o timer cobre eventuais falhas. Depois de validado, desabilitar:

```bash
sudo systemctl disable --now ses-s3-mailbox-worker.timer
```

## Uso

### Instalar dependências

```bash
pip install -r requirements.txt
```

### Executar migração do banco (uma vez)

```bash
python3 worker/migrate.py
```

### Modo SQS (produção)

```bash
python3 -m worker.sqs_worker
```

Como serviço systemd:

```bash
bash scripts/install_sqs_worker_systemd.sh
```

### Modo polling S3 (fallback / manual)

```bash
python3 worker/worker.py
```

O timer systemd (`ses-s3-mailbox-worker.timer`) pode ser mantido como fallback, mas deve ser desabilitado quando SQS estiver ativo:

```bash
sudo systemctl disable --now ses-s3-mailbox-worker.timer
sudo systemctl start ses-s3-mailbox-worker.service   # manual, se necessário
```

## Verificação

**Logs SQS:**
```bash
journalctl -u ses-s3-mailbox-sqs-worker -f
```

**Logs polling:**
```bash
journalctl -u ses-s3-mailbox-worker.service -n 50 --no-pager
```

**Banco de dados:**
```bash
sqlite3 data/mailbox.db "SELECT id, s3_key, sender, subject, status FROM messages ORDER BY id DESC LIMIT 5;"
```

**Bucket S3:**
```bash
aws s3 ls s3://ricardo-vc-ses-mailbox/incoming/ --recursive
aws s3 ls s3://ricardo-vc-ses-mailbox/processed/ --recursive
aws s3 ls s3://ricardo-vc-ses-mailbox/failed/ --recursive
```

## Fluxo detalhado

1. SES recebe e-mail → salva no bucket S3 prefixo `incoming/`
2. S3 dispara evento `ObjectCreated:Put` → entrega na fila SQS
3. `sqs_worker.py` faz long polling na fila
4. Para cada registro S3 no evento:
   - decodifica a key (URL-encoded)
   - valida bucket e prefixo `incoming/`
   - ignora `AMAZON_SES_SETUP_NOTIFICATION`
   - baixa o `.eml` para `data/raw-emails/`
   - extrai cabeçalhos (From, To, Cc, Bcc, Subject, Date, In-Reply-To, References, X-SES-*)
   - calcula `thread_id`
   - entrega no Maildir `data/maildir/master/new/`
   - registra metadados no SQLite
   - move objeto S3 para `processed/` (sucesso) ou `failed/` (erro)
5. SQS message deletada após todos os registros processados
6. Em caso de erro transiente, mensagem volta para fila após visibility timeout
7. Dovecot lê o Maildir → Thunderbird acessa via IMAP

## Outbound SMTP mode

Envio de e-mails via SMTP local → relay SES → cópia local em `.Sent` + SQLite.

```
Thunderbird
    ↓
SMTP local (sender/smtp_server.py) na porta 2525
    ↓
relay via Amazon SES SMTP (email-smtp.us-east-1.amazonaws.com:587)
    ↓
destinatário externo
    ↓
cópia local: data/raw-outbound/ + data/maildir/master/.Sent/ + SQLite
```

### 1. Credenciais SES SMTP

As credenciais SMTP do SES **não são** as mesmas da AWS CLI. Gerar em:
**AWS Console → SES → SMTP Settings → Create SMTP Credentials**.

Configurar no `.env`:

```env
SES_SMTP_USERNAME=AKIA...       # IAM user com permissão ses:SendRawEmail
SES_SMTP_PASSWORD=BM...          # senha SMTP (não Access Key)
SES_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SES_SMTP_PORT=587
SES_SMTP_STARTTLS=true
```

### 2. Domínio/remetente verificado

- O domínio `inbox.ricardo.vc` deve estar verificado no SES.
- Se a conta SES estiver em **sandbox**, só pode enviar para destinatários verificados.
- O `From:` do e-mail e o envelope `MAIL FROM` devem ser de um domínio/identidade verificada.

### 3. DKIM e DMARC (entregabilidade)

O SES aceita o relay mesmo sem DKIM próprio, mas provedores como Gmail aplicam **DMARC** e rejeitam e-mails sem assinatura DKIM alinhada ao domínio do `From:`.

```
From: teste@inbox.ricardo.vc
DKIM: d=amazonses.com       ← não alinhado → rejeitado pelo Gmail
DKIM: d=inbox.ricardo.vc    ← alinhado       → aceito
```

Erro comum sem DKIM:

```
550-5.7.26 Unauthenticated email from ricardo.vc is not accepted
due to domain's DMARC policy.
```

O Terraform já inclui Easy DKIM (`aws_ses_domain_dkim`) e publica os 3 registros CNAME no Cloudflare:

```bash
cd terraform && terraform apply
aws ses get-identity-dkim-attributes --identities inbox.ricardo.vc --region us-east-1
# Esperado: DkimVerificationStatus = Success
```

### 4. Iniciar SMTP sender manualmente

```bash
python3 -m sender.smtp_server
```

### 5. Instalar como serviço systemd

```bash
bash scripts/install_smtp_sender_systemd.sh
```

### 6. Configurar Thunderbird

```
Servidor SMTP: <IP da VM>
Porta: 2525
Segurança: Nenhuma (STARTTLS opcional futuro)
Autenticação: Nenhuma (controle por IP)
```

### 7. Segurança

- A porta 2525 **não deve ser exposta à internet**.
- Apenas IPs na variável `LOCAL_SMTP_ALLOWED_NETWORKS` podem conectar.
- Configuração padrão: `127.0.0.1/32,10.10.10.0/24,100.64.0.0/10` (localhost + Tailscale).
- Autenticação SMTP pode ser implementada futuramente.

### 8. Verificar envio

**Logs:**
```bash
journalctl -u ses-s3-mailbox-smtp-sender -f
```

**SQLite:**
```bash
sqlite3 data/mailbox.db "SELECT id, sender, recipient, subject, direction, status, sent_at FROM messages WHERE direction='outbound' ORDER BY id DESC LIMIT 5;"
```

**Maildir Sent:**
```bash
ls -la data/maildir/master/.Sent/cur/
```

**Porta:**
```bash
ss -lntp | grep 2525
```

### 9. Fluxo de falha

Se o relay SES falhar (credenciais inválidas, rede, etc):

- O e-mail é salvo em `data/raw-outbound/` mesmo assim
- O status no SQLite é `failed` com `error_message`
- O cliente SMTP recebe erro `550`
- O e-mail **não** é entregue ao destinatário

## Sent deduplication

O backend (`sender/store.py`) salva uma cópia de cada e-mail enviado em `.Sent/cur/`. O Thunderbird também salva uma cópia via IMAP/Dovecot ao enviar. Isso gera duas cópias do mesmo e-mail na pasta de enviados.

O deduplicador resolve isso automaticamente por `Message-ID`:

- Mantém a cópia registrada no SQLite (`local_maildir_path`)
- Move as duplicatas para `.SentDuplicates/cur/` (quarentena, nunca apaga)

### Rodar manualmente

```bash
python3 -m sender.dedupe_sent
```

### Instalar timer automático (a cada 2 min)

```bash
bash scripts/install_sent_dedupe_systemd.sh
```

### Verificar

```bash
journalctl -u ses-s3-mailbox-sent-dedupe.service -n 10 --no-pager
find data/maildir/master/.Sent/cur -type f
find data/maildir/master/.SentDuplicates -type f
```

## Delivery status tracking

O SES aceitar o relay (`status = accepted_by_ses`) não garante entrega final. O servidor de destino pode rejeitar após aceitar a conexão (ex: DMARC, spam, caixa cheia). Nesse caso o SES envia um bounce/DSN de volta.

O worker inbound detecta bounces automaticamente e atualiza o outbound original:

| status | significado |
|---|---|
| `accepted_by_ses` | SES aceitou o relay SMTP |
| `bounced` | destinatário/servidor remoto rejeitou |
| `failed` | falha local antes do SES aceitar |
| `delivered` | (futuro) entrega confirmada via SES events |
| `complaint` | (futuro) reclamação de spam |

### Como funciona

1. E-mail de bounce chega via SES Receiving → S3 → SQS → worker
2. `worker/bounce.py` parseia o `message/delivery-status` e extrai:
   - `Final-Recipient`, `Action`, `Status`, `Diagnostic-Code`
   - `Message-ID`, `From`, `Subject` do original (via `message/rfc822`)
3. Localiza o outbound original no SQLite (por subject + recipient)
4. Atualiza `status = bounced`, `delivery_action`, `delivery_status`, `diagnostic_code`, `bounced_at`
5. Insere linha em `message_events` para auditoria
6. O bounce inbound continua salvo normalmente no Maildir

### Verificar

```bash
sqlite3 data/mailbox.db "SELECT id, recipient, subject, status, delivery_status, bounced_at FROM messages WHERE status='bounced';"
sqlite3 data/mailbox.db "SELECT * FROM message_events WHERE event_type='bounce' ORDER BY id DESC LIMIT 3;"
```
