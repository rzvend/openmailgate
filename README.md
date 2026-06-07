# OpenMailGate

**English:** OpenMailGate is an open source hybrid email gateway and mailbox system for custom domains. It combines Amazon SES, S3, SQS, Docker, IMAP/SMTP, a web dashboard, CLI tools and OpenTofu automation.

**Português:** OpenMailGate é uma solução open source e híbrida para hospedar e administrar e-mails com domínio próprio. Ela combina Amazon SES, S3, SQS, Docker, IMAP/SMTP, dashboard web, ferramentas de CLI e automação com OpenTofu.

> Status: `v0.1.0-alpha` — alpha release / release alpha

This project is in alpha. It is intended for technical users, self-hosters, homelabs and small businesses that understand Docker, DNS and basic cloud infrastructure.

Este projeto está em fase alpha. Ele é voltado a usuários técnicos, self-hosters, homelabs e pequenos negócios com familiaridade básica com Docker, DNS e infraestrutura cloud.

---

## What is OpenMailGate? / O que é o OpenMailGate?

OpenMailGate uses AWS as the external email edge while keeping the final mailbox storage under your control.

O OpenMailGate usa a AWS como borda externa de e-mail, mantendo o armazenamento final das caixas sob seu controle.

Inbound mail flow / Fluxo de entrada:

```text
Internet → Amazon SES → S3 → SQS → worker-sqs → Maildir → Dovecot/IMAP → email client
```

Outbound mail flow / Fluxo de saída:

```text
Email client → smtp-sender → Amazon SES → external recipient
```

Setup flow / Fluxo de setup:

```text
Dashboard → AWS/Cloudflare validation → IAM preflight → OpenTofu init/plan/apply
→ post-apply validation → first mailbox
```

OpenMailGate is useful when you want professional email with your own domain but do not want to expose a traditional public SMTP server from a home connection, small office, homelab or private infrastructure.

O OpenMailGate é útil quando você quer e-mail profissional com domínio próprio, mas não quer expor diretamente um servidor SMTP público tradicional a partir de uma conexão residencial, pequeno escritório, homelab ou infraestrutura privada.

---

## Why? / Por quê?

Running a traditional mail server is hard. You usually need a public IPv4 address, open SMTP ports, reverse DNS, good IP reputation, careful DNS configuration and ongoing maintenance.

Manter um servidor de e-mail tradicional é difícil. Normalmente você precisa de IPv4 público, portas SMTP abertas, DNS reverso, boa reputação de IP, configuração DNS cuidadosa e manutenção contínua.

OpenMailGate takes a different approach:

* Amazon SES handles the public email edge.
* S3 temporarily stores inbound messages.
* SQS notifies the local worker.
* Dovecot exposes local Maildir storage over IMAP.
* A local SMTP service relays outbound email through SES.
* The dashboard and OpenTofu automate much of the setup.

O OpenMailGate segue outro caminho:

* Amazon SES cuida da borda pública de e-mail.
* S3 armazena temporariamente as mensagens recebidas.
* SQS notifica o worker local.
* Dovecot expõe o armazenamento local Maildir via IMAP.
* Um serviço SMTP local envia mensagens pela Amazon SES.
* O dashboard e o OpenTofu automatizam boa parte da configuração.

This can help in scenarios with CGNAT, blocked ports, no clean public IPv4, poor VPS IP reputation, or when you want to keep mailbox storage on your own server, NAS, homelab or private infrastructure.

Isso pode ajudar em cenários com CGNAT, portas bloqueadas, ausência de IPv4 público limpo, má reputação de IP de VPS, ou quando você quer manter o armazenamento das caixas no seu próprio servidor, NAS, homelab ou infraestrutura privada.

---

## Main features / Principais recursos

* Hybrid AWS + self-hosted architecture.
  Arquitetura híbrida AWS + self-hosted.

* Inbound email via Amazon SES, S3 and SQS.
  Recebimento via Amazon SES, S3 e SQS.

* Local Maildir storage.
  Armazenamento local em Maildir.

* IMAP access through Dovecot.
  Acesso IMAP via Dovecot.

* Outbound SMTP relay through Amazon SES.
  Envio SMTP via Amazon SES.

* Web dashboard for setup and administration.
  Dashboard web para setup e administração.

* OpenTofu-based infrastructure automation for AWS and Cloudflare.
  Automação de infraestrutura baseada em OpenTofu para AWS e Cloudflare.

* Runtime environment sync after infrastructure creation.
  Sincronização de variáveis runtime após criação da infraestrutura.

* First mailbox wizard.
  Wizard de primeira mailbox.

* CLI tools for administration.
  Ferramentas CLI de administração.

* Optional master mailbox/audit copy concept.
  Conceito de caixa master/cópia de auditoria.

* Docker Compose based deployment.
  Deploy via Docker Compose.

---

## How OpenMailGate compares / Comparativo resumido

| Category / Categoria                               | Typical limitation / Limitação típica                                                                                                                                            | OpenMailGate difference / Diferencial                                                                                                              |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mailcow / Mailu / Stalwart                         | Usually require public SMTP, IPv4, open ports, reverse DNS and IP reputation management. / Normalmente exigem SMTP público, IPv4, portas abertas, DNS reverso e reputação de IP. | Uses AWS as the external email edge while keeping mailboxes local. / Usa AWS como borda externa e mantém as caixas localmente.                     |
| SES + S3 DIY                                       | Powerful but manual; no integrated dashboard, mailbox workflow or reproducible setup. / Poderoso, mas manual; sem dashboard, mailbox integrada ou instalação reproduzível.       | Packages SES/S3/SQS into a Docker-based tool with dashboard, CLI and IaC. / Empacota SES/S3/SQS em uma ferramenta Docker com dashboard, CLI e IaC. |
| SES + Dovecot tutorials                            | Usually one-off guides, not an integrated product. / Geralmente são guias pontuais, não um produto integrado.                                                                    | Turns the architecture into an installable and administrable project. / Transforma a arquitetura em um projeto instalável e administrável.         |
| Plunk / Postal                                     | Focused on transactional email, campaigns or automation. / Focados em e-mail transacional, campanhas ou automações.                                                              | Focuses on professional IMAP/SMTP mailboxes with local storage. / Foca em caixas IMAP/SMTP com armazenamento local.                                |
| WorkMail / Google Workspace / Microsoft 365 / Zoho | Convenient, but usually billed per user and stores mail inside the provider. / Convenientes, mas normalmente cobrados por usuário e com armazenamento no provedor.               | Lower incremental cost per mailbox, local storage and more control. / Menor custo incremental por caixa, armazenamento local e mais controle.      |

OpenMailGate does not try to replace full collaboration suites or mature mail server distributions. It occupies a middle ground between hosted email suites, traditional self-hosted mail servers and DIY SES/S3 scripts.

O OpenMailGate não tenta substituir suítes completas de colaboração nem distribuições maduras de mail server. Ele ocupa um espaço intermediário entre suítes hospedadas, servidores de e-mail tradicionais e scripts DIY com SES/S3.

---

## Current alpha status / Estado atual do alpha

The following clean-install milestones have been validated:

* Docker Compose stack starts successfully.
* Dashboard first-run works.
* AWS and Cloudflare credentials validation works.
* IAM preflight works.
* OpenTofu `init`, `plan` and `apply` work from the dashboard.
* SES domain identity, DKIM, receipt rules and Custom MAIL FROM are created.
* S3 bucket, S3 notification and SQS queue are created.
* Cloudflare DNS records are created.
* Runtime outputs are synced into `.env`.
* First mailbox can be created from the dashboard.
* Dovecot IMAP works.
* Outbound SMTP through SES works.
* Thunderbird can send email.
* Sent folder works.
* Replies are received through SES/S3/SQS and delivered to IMAP.

Validações limpas recentes:

```text
G.2.6 — Clean Reinstall after bug fixes
Status: approved with fixes during validation

G.2.7 — Final clean install release candidate
Status: approved
```

---

## Requirements / Requisitos

### Host

* Linux VM or server.
  VM ou servidor Linux.

* Recommended: Debian 12/13, Ubuntu 24.04 or compatible.
  Recomendado: Debian 12/13, Ubuntu 24.04 ou compatível.

* 2 vCPU minimum.
  Mínimo de 2 vCPU.

* 2 GB RAM minimum, 4 GB recommended.
  Mínimo de 2 GB RAM, recomendado 4 GB.

* 20 GB disk minimum.
  Mínimo de 20 GB de disco.

* Docker Engine.

* Docker Compose plugin.

* Git.

### AWS account and IAM credentials / Conta AWS e credenciais IAM

You need an AWS account and an IAM access key that the setup wizard can use to create and validate the required resources.

Você precisa de uma conta AWS e de uma access key de IAM que o wizard de setup possa usar para criar e validar os recursos necessários.

Required values in `.env` / Valores necessários no `.env`:

```env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_iam_access_key_id
AWS_SECRET_ACCESS_KEY=your_iam_secret_access_key
```

Do **not** use AWS root account access keys.

Não use access keys da conta root da AWS.

Use a dedicated IAM user for OpenMailGate setup.

Use um usuário IAM dedicado para o setup do OpenMailGate.

### AWS managed policies for the setup IAM user / Políticas AWS para o usuário IAM de setup

For alpha testing, there are two possible approaches.

Para testes alpha, há duas abordagens possíveis.

#### Option A — simplest alpha setup / Opção A — setup alpha mais simples

Create a dedicated IAM user for OpenMailGate setup and attach:

Crie um usuário IAM dedicado para o setup do OpenMailGate e anexe:

```text
AdministratorAccess
```

This is the simplest path for alpha testing because it allows OpenTofu to create all required SES, S3, SQS, IAM and related resources.

Esse é o caminho mais simples para testes alpha, porque permite que o OpenTofu crie todos os recursos necessários de SES, S3, SQS, IAM e recursos relacionados.

Use this only for testing or initial alpha validation. For long-term use, replace it with narrower permissions.

Use essa opção apenas para testes ou validação inicial do alpha. Para uso de longo prazo, substitua por permissões mais restritas.

#### Option B — more restricted alpha setup / Opção B — setup alpha mais restrito

Instead of `AdministratorAccess`, you can attach these AWS managed policies:

Em vez de `AdministratorAccess`, você pode anexar estas políticas gerenciadas da AWS:

```text
AmazonSESFullAccess
AmazonS3FullAccess
AmazonSQSFullAccess
IAMFullAccess
```

These policies cover the currently required OpenMailGate setup resources:

Essas políticas cobrem os recursos atualmente necessários no setup do OpenMailGate:

* SES domain identity, DKIM, receipt rules and Custom MAIL FROM.
  SES domain identity, DKIM, receipt rules e Custom MAIL FROM.

* S3 bucket, bucket policy and S3 notification.
  Bucket S3, bucket policy e notificação S3.

* SQS queue and queue policy.
  Fila SQS e queue policy.

* IAM user, access key and policy for the SES SMTP relay.
  Usuário IAM, access key e policy para o relay SMTP via SES.

For production or long-term deployments, create a least-privilege customer-managed policy after reviewing the OpenTofu plan and the exact AWS actions required.

Para produção ou uso de longo prazo, crie uma policy própria de menor privilégio depois de revisar o OpenTofu plan e as ações AWS exatas exigidas.

### AWS SES production access / Acesso de produção do Amazon SES

If your AWS SES account is still in the SES sandbox, outbound email may only be allowed to verified recipients.

Se sua conta AWS ainda estiver no sandbox do SES, o envio externo pode ficar limitado a destinatários verificados.

For real email sending, request **SES production access** in the AWS region used by OpenMailGate, for example:

Para envio real de e-mails, solicite **SES production access** na região usada pelo OpenMailGate, por exemplo:

```env
AWS_REGION=us-east-1
```

OpenMailGate can create and validate the SES domain identity, DKIM records and Custom MAIL FROM records, but SES account sending limits and sandbox/production status are controlled by AWS.

O OpenMailGate pode criar e validar a domain identity, os registros DKIM e o Custom MAIL FROM, mas limites de envio e status sandbox/produção do SES são controlados pela AWS.

### SES SMTP credentials / Credenciais SMTP do SES

OpenMailGate also needs SES SMTP credentials for outbound mail.

O OpenMailGate também precisa de credenciais SMTP do SES para envio de e-mails.

In the normal dashboard/OpenTofu flow, you should **not manually create these credentials**.

No fluxo normal via dashboard/OpenTofu, você **não deve criar essas credenciais manualmente**.

They are created automatically during infrastructure setup and then synced into `.env`:

Elas são criadas automaticamente durante o setup da infraestrutura e depois sincronizadas para o `.env`:

```env
SES_SMTP_USERNAME=generated_by_opentofu
SES_SMTP_PASSWORD=generated_by_opentofu
SES_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SES_SMTP_PORT=587
```

`SES_SMTP_USERNAME` and `SES_SMTP_PASSWORD` are different from `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

`SES_SMTP_USERNAME` e `SES_SMTP_PASSWORD` são diferentes de `AWS_ACCESS_KEY_ID` e `AWS_SECRET_ACCESS_KEY`.

### Cloudflare

You need a Cloudflare-managed DNS zone for the domain or parent domain.

Você precisa de uma zona DNS gerenciada pela Cloudflare para o domínio ou domínio pai.

Required values in `.env` / Valores necessários no `.env`:

```env
CLOUDFLARE_ZONE_ID=your_cloudflare_zone_id
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
```

The Cloudflare API token must be able to read the zone and manage DNS records in that zone.

O token de API da Cloudflare precisa conseguir ler a zona e gerenciar registros DNS nessa zona.

Minimum expected permissions:

Permissões mínimas esperadas:

```text
Zone: Read
DNS: Read
DNS: Edit
```

OpenMailGate uses this token to create or validate records such as:

O OpenMailGate usa esse token para criar ou validar registros como:

* MX for inbound SES receiving.
  MX para recebimento via SES.

* TXT for SPF.
  TXT para SPF.

* TXT for SES domain verification.
  TXT para verificação de domínio SES.

* CNAME records for SES DKIM.
  CNAMEs de DKIM do SES.

* MX/TXT records for SES Custom MAIL FROM.
  Registros MX/TXT do Custom MAIL FROM do SES.

### Domain / Domínio

You need a domain or subdomain dedicated to the OpenMailGate deployment.

Você precisa de um domínio ou subdomínio dedicado ao OpenMailGate.

Example / Exemplo:

```env
MAIL_DOMAIN=alpha.example.com
```

For alpha testing, using a subdomain is recommended.

Para testes alpha, recomenda-se usar um subdomínio.

### Client / Cliente

* Thunderbird or another IMAP/SMTP client.
  Thunderbird ou outro cliente IMAP/SMTP.

---

## Security warning / Aviso de segurança

The `.env` file contains sensitive secrets.

O arquivo `.env` contém segredos sensíveis.

Never commit `.env`.

Nunca faça commit do `.env`.

Protect it:

Proteja o arquivo:

```bash
chmod 600 .env
```

Do not paste these values into public chats, issues or logs:

Não cole estes valores em chats públicos, issues ou logs:

```text
AWS_SECRET_ACCESS_KEY
CLOUDFLARE_API_TOKEN
SES_SMTP_PASSWORD
SESSION_SECRET
```

If a secret is exposed, rotate it.

Se algum segredo for exposto, faça rotação.

Always review the OpenTofu plan before applying. The setup creates or updates cloud resources that may generate costs.

Sempre revise o OpenTofu plan antes do apply. O setup cria ou altera recursos cloud que podem gerar custos.

---

## Quick install / Instalação rápida

> This alpha flow assumes Cloudflare DNS and AWS SES/S3/SQS.
> Este fluxo alpha assume DNS na Cloudflare e AWS SES/S3/SQS.

Before continuing, prepare:

Antes de continuar, tenha em mãos:

```text
AWS IAM Access Key ID
AWS IAM Secret Access Key
Cloudflare Zone ID
Cloudflare API Token
Domain or subdomain for OpenMailGate
```

### 1. Install Docker / Instalar Docker

On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y git curl ca-certificates gnupg
```

Install Docker using the official Docker repository for your distribution.

Instale o Docker usando o repositório oficial do Docker para sua distribuição.

After installation, allow your user to use Docker:

Após a instalação, permita que seu usuário use Docker:

```bash
sudo usermod -aG docker "$USER"
```

Log out and log in again, or run:

Saia e entre novamente na sessão, ou execute:

```bash
newgrp docker
```

Validate:

Valide:

```bash
docker --version
docker compose version
docker ps
```

---

### 2. Clone the repository / Clonar o repositório

```bash
git clone https://github.com/YOUR_ORG/openmailgate.git
cd openmailgate
```

For the current private/internal repository, use your configured Forgejo/Git remote.

Para o repositório privado/interno atual, use o remote Git/Forgejo configurado.

Check status:

Confira o estado:

```bash
git status
git log --oneline -5
```

Expected:

Esperado:

```text
working tree clean
```

---

### 3. Create `.env` / Criar `.env`

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Fill only the minimum required values:

Preencha apenas os valores mínimos necessários:

```env
SESSION_SECRET=replace_with_a_long_random_secret

MAIL_DOMAIN=alpha.example.com

AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=replace_me
AWS_SECRET_ACCESS_KEY=replace_me

CLOUDFLARE_ZONE_ID=replace_me
CLOUDFLARE_API_TOKEN=replace_me

API_BIND=YOUR_VM_IP
IMAP_BIND=YOUR_VM_IP
SMTP_BIND=YOUR_VM_IP
```

Do not manually fill these before the infrastructure setup:

Não preencha manualmente estes campos antes do setup da infraestrutura:

```env
S3_BUCKET=
SQS_QUEUE_URL=
SES_SMTP_USERNAME=
SES_SMTP_PASSWORD=
```

They are expected to be created by OpenTofu and synced later through the dashboard.

Eles devem ser criados pelo OpenTofu e sincronizados depois pelo dashboard.

---

### 4. Validate Docker Compose / Validar Docker Compose

```bash
docker compose config
```

Expected:

Esperado:

```text
No obsolete "version" warning
No rendering errors
MAIL_DOMAIN correctly rendered
API/IMAP/SMTP binds correctly rendered
```

---

### 5. Start the stack / Subir a stack

```bash
docker compose up -d --build
docker compose ps
```

Expected services:

Serviços esperados:

```text
api
dovecot
smtp-sender
worker-sqs
```

Test the API:

Teste a API:

```bash
curl -i http://YOUR_VM_IP:8000/health
```

Expected:

Esperado:

```text
HTTP/1.1 200 OK
```

---

### 6. Open the dashboard / Abrir o dashboard

Open:

Abra:

```text
http://YOUR_VM_IP:8000
```

Follow the first-run flow:

Siga o fluxo inicial:

```text
/setup
→ create first admin
→ login
```

---

### 7. Validate AWS and Cloudflare / Validar AWS e Cloudflare

In the dashboard:

No dashboard:

```text
Setup → Credentials → Validate AWS/Cloudflare
```

Expected:

Esperado:

```text
AWS STS OK
Cloudflare zone OK
```

---

### 8. IAM preflight

In the dashboard:

No dashboard:

```text
Setup → IAM Preflight
```

Expected:

Esperado:

```text
ready
```

If the IAM user already has the maximum number of access keys, follow the dashboard guidance before continuing.

Se o usuário IAM já tiver o número máximo de access keys, siga a orientação do dashboard antes de continuar.

---

### 9. Run OpenTofu init/plan/apply

In the dashboard:

No dashboard:

```text
Infrastructure Setup
→ Run init
→ Run plan
```

Review the plan carefully.

Revise o plan com atenção.

Expected for a fresh alpha install:

Esperado para uma instalação alpha limpa:

```text
Plan: 23 to add, 0 to change, 0 to destroy
```

Do not apply if there are unexpected destroys.

Não execute apply se houver destroys inesperados.

Then:

Depois:

```text
Run apply
```

Expected:

Esperado:

```text
Apply complete
```

---

### 10. Sync runtime environment / Sincronizar ambiente runtime

After apply, run the dashboard action to update the runtime `.env`.

Após o apply, execute a ação do dashboard para atualizar o `.env` runtime.

Expected updated keys:

Chaves esperadas:

```text
DEFAULT_FROM_DOMAIN
S3_BUCKET
SQS_QUEUE_URL
SES_SMTP_USERNAME
SES_SMTP_PASSWORD
```

Because Docker Compose `env_file` values are loaded when containers are created, recreate the services:

Como valores de `env_file` do Docker Compose são carregados quando os containers são criados, recrie os serviços:

```bash
docker compose up -d --force-recreate api worker-sqs smtp-sender
```

Validate:

Valide:

```bash
docker compose ps
curl -i http://YOUR_VM_IP:8000/health
```

---

### 11. Post-apply validation / Validação pós-apply

In the dashboard:

No dashboard:

```text
Post-apply validation → Run validation
```

Expected:

Esperado:

```text
AWS STS OK
S3 OK
SQS OK
SES identity OK
SES DKIM OK
SES receipt rule OK
SES MAIL FROM OK
Cloudflare DNS OK
MAIL FROM MX OK
MAIL FROM SPF OK
```

---

### 12. Create the first mailbox / Criar a primeira mailbox

In the dashboard:

No dashboard:

```text
First mailbox
```

Create, for example:

Crie, por exemplo:

```text
user@alpha.example.com
```

The dashboard should:

O dashboard deve:

* create the mailbox;
  criar a mailbox;

* create the email address;
  criar o endereço de e-mail;

* create the Maildir structure;
  criar a estrutura Maildir;

* write `/app/dovecot/users`;
  escrever `/app/dovecot/users`;

* show IMAP/SMTP instructions.
  mostrar as instruções de IMAP/SMTP.

Restart Dovecot when instructed:

Reinicie o Dovecot quando orientado:

```bash
docker compose restart dovecot
```

---

### 13. Validate IMAP/Maildir / Validar IMAP/Maildir

Replace the email address below:

Substitua o endereço abaixo:

```bash
docker compose exec dovecot doveadm user user@alpha.example.com
docker compose exec dovecot doveadm mailbox list -u user@alpha.example.com
docker compose exec dovecot doveadm mailbox status -u user@alpha.example.com messages Sent
```

Test writing to `Sent`:

Teste gravação em `Sent`:

```bash
printf "From: test@example.com\nSubject: append test\n\nok\n" | \
  docker compose exec -T dovecot doveadm save -u user@alpha.example.com -m Sent
```

Check again:

Confira novamente:

```bash
docker compose exec dovecot doveadm mailbox status -u user@alpha.example.com messages Sent
```

Expected:

Esperado:

```text
No Permission denied
Sent messages increases
```

---

### 14. Configure Thunderbird / Configurar Thunderbird

IMAP:

```text
Server: YOUR_VM_IP
Port: 143
Connection security: None
Authentication: Normal password
Username: user@alpha.example.com
Password: password created in dashboard
```

SMTP:

```text
Server: YOUR_VM_IP
Port: 2525
Connection security: None
Authentication: None
Username: blank
```

Send a test email to an external mailbox.

Envie um e-mail de teste para uma caixa externa.

Expected:

Esperado:

```text
Email is delivered
Copy is saved in Sent
No "Copying to Sent" error
```

Reply from the external mailbox.

Responda a partir da caixa externa.

Expected:

Esperado:

```text
Reply is received in Thunderbird
Message is stored locally through Maildir/Dovecot
```

---

## Known alpha limitations / Limitações conhecidas do alpha

* This is not production-ready yet.
  Ainda não é considerado pronto para produção.

* TLS/HTTPS/IMAPS/secure SMTP are planned for production hardening.
  TLS/HTTPS/IMAPS/SMTP seguro fazem parte do hardening futuro.

* PostgreSQL support is future/optional.
  Suporte a PostgreSQL é futuro/opcional.

* RBAC and multi-user admin roles are future work.
  RBAC e múltiplos administradores com papéis distintos são trabalhos futuros.

* Backup/restore tooling should be reviewed before production use.
  Backup/restore deve ser revisado antes de uso em produção.

* Some automated tests are currently outdated or failing and need triage.
  Alguns testes automatizados estão desatualizados ou falhando e precisam de triagem.

* The project currently assumes AWS and Cloudflare for the automated setup path.
  O fluxo automatizado atual assume AWS e Cloudflare.

* AWS resources may generate costs.
  Recursos AWS podem gerar custos.

---

## Documentation / Documentação

Useful documents:

Documentos úteis:

```text
docs/deploy-docker.md
docs/security-alpha.md
docs/operations.md
docs/backup-restore.md
docs/s3-lifecycle.md
docs/troubleshooting-iac.md
docs/validation-g26.md
docs/validation-g27.md
```

---

## Roadmap / Roteiro

### English

OpenMailGate `v0.1.0-alpha` focuses on the first working Docker-based setup flow:

* dashboard first-run;
* AWS/Cloudflare validation;
* OpenTofu-based infrastructure setup;
* SES/S3/SQS inbound mail flow;
* SES SMTP outbound relay;
* Dovecot IMAP access;
* first mailbox creation;
* Thunderbird-compatible IMAP/SMTP usage.

Future versions may include:

* HTTPS support for the dashboard;
* TLS for IMAP/SMTP;
* optional PostgreSQL backend;
* improved backup and restore tooling;
* Docker secrets or other secret-management options;
* multi-admin support and RBAC;
* audit logs and operational metrics;
* optional webmail integration;
* guided import/adopt mode for existing AWS/Cloudflare resources;
* safer DKIM adoption for existing SES identities;
* improved test coverage and CI validation;
* production hardening documentation.

### Português

O OpenMailGate `v0.1.0-alpha` tem como foco o primeiro fluxo funcional de instalação via Docker:

* first-run pelo dashboard;
* validação AWS/Cloudflare;
* setup de infraestrutura com OpenTofu;
* recebimento via SES/S3/SQS;
* envio SMTP via SES;
* acesso IMAP via Dovecot;
* criação da primeira mailbox;
* uso via Thunderbird ou outro cliente IMAP/SMTP.

Versões futuras poderão incluir:

* suporte HTTPS para o dashboard;
* TLS para IMAP/SMTP;
* backend PostgreSQL opcional;
* melhorias em backup e restore;
* Docker secrets ou outras opções de gerenciamento de segredos;
* múltiplos administradores e RBAC;
* logs de auditoria e métricas operacionais;
* integração opcional com webmail;
* modo guiado de importação/adoção de recursos AWS/Cloudflare existentes;
* adoção mais segura de DKIM para identities SES existentes;
* melhoria da cobertura de testes e validação CI;
* documentação de hardening para produção.

---

## License / Licença

OpenMailGate is free software licensed under the GNU Affero General Public License v3.0 or later.

OpenMailGate é software livre licenciado sob a GNU Affero General Public License v3.0 ou posterior.

Recommended attribution:

Atribuição recomendada:

```text
OpenMailGate — Copyright (C) 2026 Ricardo Z. Vendramini.
Licensed under the GNU AGPL-3.0-or-later.
```

Redistributions, forks and modified versions must preserve copyright notices, license notices and attribution to the original project and original author in accordance with the GNU AGPL-3.0-or-later.

Redistribuições, forks e versões modificadas devem preservar os avisos de copyright, licença e atribuição ao projeto original e ao autor original, conforme a GNU AGPL-3.0-or-later.

---

## Trademark and affiliation notice / Aviso de marcas e afiliação

This project is not affiliated with, endorsed by or sponsored by Amazon Web Services.

Este projeto não é afiliado, endossado nem patrocinado pela Amazon Web Services.

Amazon Web Services, AWS, Amazon SES, Amazon S3 and Amazon SQS are trademarks of their respective owners.

Amazon Web Services, AWS, Amazon SES, Amazon S3 e Amazon SQS são marcas de seus respectivos proprietários.

Third-party names, trademarks, libraries, services and software belong to their respective owners.

Nomes, marcas, bibliotecas, serviços e softwares de terceiros pertencem aos seus respectivos proprietários.
