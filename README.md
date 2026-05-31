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
│   ├── setup_sqs_s3_notifications.sh    # configura SQS policy + S3 notification
│   └── install_sqs_worker_systemd.sh    # instala serviço systemd
├── systemd/
│   └── ses-s3-mailbox-sqs-worker.service
├── worker/
│   ├── __init__.py
│   ├── worker.py         # modo polling S3 (fallback)
│   ├── sqs_worker.py     # daemon SQS long polling (produção)
│   └── migrate.py        # migração do SQLite
├── data/
│   ├── mailbox.db        # SQLite (não versionado)
│   ├── raw-emails/       # e-mails brutos (não versionado)
│   └── maildir/          # Maildir do Dovecot (não versionado)
└── terraform/            # infraestrutura AWS
```

## Pré-requisitos

- Python 3.11+
- boto3, python-dotenv (`pip install -r requirements.txt`)
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
