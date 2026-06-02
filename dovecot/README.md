# Dovecot Virtual Users — Configuração Multi-Mailbox

## Abordagem

**Híbrida**: uma conta IMAP por mailbox agora, dashboard/API como camada administrativa principal no futuro.

Dovecot é apenas a camada de acesso IMAP — a regra de negócio está no banco (`mailboxes`, `email_addresses`, `message_mailboxes`) e no worker.

## Estado atual

- Login `ricardo` via PAM → abre a `master` (preservado)
- Login `teste@inbox.ricardo.vc` via passwd-file → abre a `master`
- Login `financeiro@inbox.ricardo.vc` via passwd-file → abre a `financeiro`
- `mail_location` global mantido em `maildir:~/ses-s3-mailbox/data/maildir/master`
- Cada usuário virtual tem `userdb_mail` absoluto para seu Maildir

## Arquivos envolvidos

| Arquivo | Descrição |
|---|---|
| `/etc/dovecot/conf.d/10-auth.conf` | `!include auth-passwdfile.conf.ext` antes de `auth-system.conf.ext` |
| `/etc/dovecot/conf.d/10-mail.conf` | `mail_location` global na master (não alterar para `%n`) |
| `/etc/dovecot/conf.d/auth-passwdfile.conf.ext` | Configuração do driver passwd-file |
| `/etc/dovecot/users` | Arquivo de senhas — **não versionar** |

## Gerar hash de senha

```bash
doveadm pw -s SHA512-CRYPT
# Digite a senha duas vezes
```

Copiar a linha inteira incluindo `{SHA512-CRYPT}`.

## Formato de `/etc/dovecot/users`

Ver `dovecot/users.example` neste diretório.

```
<usuario>:{SHA512-CRYPT}<hash>:1000:1000::<home>::userdb_mail=maildir:<caminho>
```

**Não versionar este arquivo com senhas reais.**

## Permissões

```bash
sudo chown root:dovecot /etc/dovecot/users
sudo chmod 640 /etc/dovecot/users
```

Dovecot roda como uid 97 (`dovecot`), precisa de leitura.

## Validar antes de reiniciar

```bash
sudo doveadm user teste@inbox.ricardo.vc
sudo doveadm auth test teste@inbox.ricardo.vc <senha>
sudo doveadm auth test financeiro@inbox.ricardo.vc <senha>
```

## Rollback

```bash
sudo cp /etc/dovecot/conf.d/10-auth.conf.bak /etc/dovecot/conf.d/10-auth.conf
sudo rm /etc/dovecot/users
sudo systemctl restart dovecot
```

## Thunderbird

```
IMAP: 10.10.10.16:143 STARTTLS Normal password
SMTP: 10.10.10.16:2525 None No authentication
User: <email completo> (ex: financeiro@inbox.ricardo.vc)
```

## Segurança

- Nunca usar `{PLAIN}` — usar `{SHA512-CRYPT}`
- Nunca versionar `/etc/dovecot/users`
- Nunca versionar senhas reais
- Trocar senhas temporárias após teste
- PAM preservado — login `ricardo` continua funcionando

## Sincronização automática (CLI)

### Definir senha IMAP (armazenada no banco)

```bash
python3 -m worker.mailbox_admin set-imap-password compras@inbox.ricardo.vc
# Solicita senha segura, gera hash SHA512-CRYPT, salva em email_addresses.imap_password_hash
```

### Gerar usuários a partir do banco

Prioridade de hash:
1. `email_addresses.imap_password_hash` (`from_db`)
2. Hash existente em `/etc/dovecot/users` (`from_file`)
3. Sem hash → `missing_hash` (não gera usuário)

```bash
# Visualizar sem alterar
sudo python3 -m worker.mailbox_admin sync-imap-users --dry-run

# Gerar em arquivo alternativo
sudo python3 -m worker.mailbox_admin sync-imap-users --output /tmp/dovecot-users

# Aplicar em /etc/dovecot/users (com backup automático)
sudo python3 -m worker.mailbox_admin sync-imap-users --apply
```

### Fluxo recomendado para nova mailbox

```bash
python3 -m worker.mailbox_admin create compras --name "Compras" --address compras@inbox.ricardo.vc
python3 -m worker.mailbox_admin set-imap-password compras@inbox.ricardo.vc
sudo python3 -m worker.mailbox_admin sync-imap-users --apply
```

Usuários com hash preservado são mantidos. Novos endereços ativos sem hash aparecem como pendentes. Usuários inativos são removidos.
