---
title: "Como criei a gitmgf em 8 horas com o Claude Pro e o Claude Code"
date: 2026-11-18
author: Diogo Carapito
summary: "Da ideia ao site em produção num dia: PRD e especificação técnica no Claude, design e logótipo com artefactos, código com o Claude Code, e publicação num VPS europeu com domínio próprio."
---

A gitmgf passou de ideia a site público em cerca de 8 horas de trabalho. Não escrevi o código à mão: escrevi o que queria, revi o que o Claude propunha e tomei as decisões. Este artigo descreve o processo, passo a passo, para quem quiser fazer o mesmo com uma ferramenta para a sua prática clínica.

**O que é preciso:** uma subscrição do Claude Pro (inclui o Claude Code), uma conta no GitHub, um domínio e um servidor virtual (VPS). Custo total aproximado: cerca de 30 € no primeiro mês e menos de 30 €/mês depois (ver o resumo no fim).

## 1. Escrever o PRD e a especificação técnica no Claude

Tudo começa num chat novo em [claude.ai](https://claude.ai) (botão **+ Novo chat**). O objetivo desta fase é chegar a dois documentos:

- **`PRD.md`** (*Product Requirements Document*): o quê e porquê. Para quem é, que problemas resolve, que funcionalidades tem o MVP, o que fica para depois, e os critérios de aceitação de cada funcionalidade.
- **`TECH_SPEC.md`**: o como. Tecnologias, modelo de dados, rotas, segurança, privacidade, testes e um plano por etapas (*milestones*), cada uma com uma "definição de concluído".

O que funcionou melhor foi pedir ao Claude que me entrevistasse antes de escrever:

> Quero criar um portal onde médicos de família partilham ferramentas digitais que criaram para a prática clínica. Faz-me perguntas, uma de cada vez, até teres informação suficiente. Depois escreve um `PRD.md` com objetivos, utilizadores, funcionalidades do MVP com critérios de aceitação, fora de âmbito e questões em aberto.

Depois, no mesmo chat:

> Com base no PRD, escreve um `TECH_SPEC.md` para um MVP simples de manter por uma pessoa: Python, FastAPI, SQLite, sem frameworks de frontend, alojado num VPS na UE com Docker. Inclui modelo de dados, segurança, RGPD, testes e milestones com definição de concluído.

Vale a pena ler tudo com calma e corrigir o que não corresponde ao que quer: estes dois ficheiros são o "contrato" que o Claude Code vai seguir. Aproveitei também para gerar um **`CLAUDE.md`** (convenções do projeto: comandos, regras de código, vocabulário em português europeu) e rascunhos dos textos legais (termos, privacidade). **Os textos legais gerados são apenas um ponto de partida e devem ser revistos por quem perceba do assunto.**

## 2. Design e logótipo com artefactos

Os artefactos do Claude mostram o resultado ao lado do chat, o que é ótimo para design. Pedi:

> Cria um mockup em HTML de uma página só com o sistema visual da gitmgf: paleta, tipografia, botões, cartões de ferramentas, página inicial, pesquisa e página de uma ferramenta, em modo claro e escuro, pensado primeiro para telemóvel.

E, à parte, o logótipo:

> Desenha um logótipo em SVG para "gitmgf": simples, legível em tamanho pequeno, com uma versão para fundo escuro.

Iterei algumas vezes ("menos sombras", "cor primária mais calma") e transferi o HTML e os SVG.

## 3. Juntar tudo numa pasta e abrir o Claude Code

Pus todos os documentos numa pasta, mais ou menos assim:

```
gitmgf/
├── PRD.md
├── TECH_SPEC.md
├── CLAUDE.md
├── design/      (mockup.html, logo.svg, logo-dark.svg)
└── legal/       (rascunhos de termos e privacidade)
```

Instalei o [Claude Code](https://claude.com/claude-code) (ver a documentação oficial para outros sistemas) e abri-o dentro da pasta:

```bash
curl -fsSL https://claude.ai/install.sh | bash
cd gitmgf
claude
```

Na primeira vez pede para iniciar sessão com a conta Claude. O primeiro pedido foi literalmente este:

> Vamos criar um MVP com os documentos que compilei, para ser publicado num VPS.

A partir daí, o Claude Code leu os documentos e construiu a aplicação etapa a etapa: base do projeto, autenticação, submissão de ferramentas, moderação, pesquisa, pontuação, conformidade e, por fim, segurança e scripts de deploy. Em cada etapa escreve testes e corre-os antes de avançar.

O que me ajudou:

- **Trabalhar por etapas.** Não avançar enquanto a etapa anterior não cumpre a definição de concluído.
- **Decidir, não programar.** Quando havia uma escolha de produto (por exemplo, trocar o login por email + palavra-passe), decidia eu e o Claude registava a decisão em `docs/DECISIONS.md`.
- **Experimentar no navegador.** Os testes passavam, mas foi ao usar o site a sério que apareceu um erro nos formulários. Testes automáticos não substituem experimentar.
- **Pausas.** O plano Pro tem limites de utilização que reiniciam ao fim de algumas horas; numa sessão longa é normal ter de esperar um pouco.

## 4. Criar um repositório público no GitHub

Com a aplicação a funcionar localmente, criei um repositório no GitHub e enviei o código. Com a [CLI do GitHub](https://cli.github.com):

```bash
git init && git add . && git commit -m "feat: MVP"
gh repo create gitmgf --public --source=. --push
```

Ou criando o repositório no site do GitHub e depois:

```bash
git remote add origin https://github.com/<utilizador>/gitmgf.git
git push -u origin main
```

**Antes de tornar público:** confirmar que o `.env` (palavras-passe, chaves) está no `.gitignore` e que nenhum segredo foi para o histórico. O código da gitmgf está em [github.com/diogocarapito/gitmgf](https://github.com/diogocarapito/gitmgf).

## 5. Comprar um domínio

Dois registos com preços justos e sem truques na renovação:

| Registo | `.com` por ano (aprox.) | Notas |
|---|---|---|
| [Cloudflare Registrar](https://www.cloudflare.com/products/registrar/) | ≈ 10–11 US$ | Preço de custo. O DNS fica na Cloudflare, que também dá proxy, HTTPS e encaminhamento de email gratuitos |
| [Porkbun](https://porkbun.com) | ≈ 11–12 US$ | Interface simples, WHOIS privado incluído |

Depois de ter o servidor (passo seguinte), cria-se no DNS um registo `A` para o domínio e outro para `www`, ambos a apontar para o IP do VPS. Na Cloudflare, com o proxy ativo, o modo SSL/TLS deve ficar em **Full (strict)**.

## 6. Alugar um VPS

Um VPS é um servidor virtual alugado ao mês. Para um MVP como este chega um servidor pequeno, mas recomendo **pelo menos 2 GB de RAM** (construir as imagens Docker com 1 GB fica apertado) e **Ubuntu 24.04 LTS**. Se a aplicação tratar dados pessoais de utilizadores europeus, um fornecedor e um centro de dados na UE simplificam o RGPD.

**Na Europa:**

| Fornecedor | Plano (exemplo) | Preço aprox. | Notas |
|---|---|---|---|
| [Hetzner](https://www.hetzner.com/cloud) (Alemanha, Finlândia) | CX23: 2 vCPU, 4 GB RAM, 40 GB | ≈ 5,5–6 €/mês | Painel excelente, faturação à hora, cópias de segurança e armazenamento de objetos no mesmo sítio |
| [netcup](https://www.netcup.com/en/server/vps) (Alemanha, Áustria) | VPS 1000 G11 | ≈ 6–8 €/mês | Muita RAM e disco pelo preço; alguns preços exigem contrato mínimo de 12 meses |

**Nos EUA:**

| Fornecedor | Plano (exemplo) | Preço aprox. |
|---|---|---|
| [DigitalOcean](https://www.digitalocean.com/pricing/droplets) | Basic, 1 GB / 2 GB | ≈ 6 / 12 US$/mês |
| [Vultr](https://www.vultr.com/pricing/) | Cloud Compute, 1 GB / 2 GB | ≈ 5 / 10 US$/mês |
| [Akamai (Linode)](https://www.linode.com/pricing/) | Nanode 1 GB / Shared 2 GB | ≈ 5 / 12 US$/mês |

A Hetzner também tem centros de dados nos EUA (Ashburn e Hillsboro). *Preços aproximados em novembro de 2026, sem IVA; mudam com frequência, por isso confirme na página de cada fornecedor.*

Ao criar o servidor, **adicione logo a sua chave SSH pública** (`cat ~/.ssh/id_ed25519.pub`; se não tiver, crie-a com `ssh-keygen -t ed25519`). Entrar por chave, e não por palavra-passe, é mais seguro e evita ficar trancado fora do servidor.

## 7. Preparar o servidor e publicar o MVP

Primeiro, como `root`, preparar o servidor: atualizações, Docker, firewall e um utilizador sem privilégios para o deploy.

```bash
ssh root@<IP-do-servidor>
apt update && apt -y upgrade
curl -fsSL https://get.docker.com | sh
adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
mkdir -p /home/deploy/.ssh && cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
ufw allow OpenSSH && ufw allow 80,443/tcp && ufw --force enable
```

**Antes de fechar esta sessão**, abra outro terminal e confirme que `ssh deploy@<IP-do-servidor>` entra. Mudanças na configuração do SSH são a forma mais comum de ficar sem acesso.

Depois, como `deploy`, descarregar o código, configurar e arrancar:

```bash
ssh deploy@<IP-do-servidor>
git clone https://github.com/<utilizador>/gitmgf.git && cd gitmgf
cp .env.example .env
nano .env          # domínio, chave secreta, email do administrador…
docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
```

Na gitmgf, o Caddy (servidor web) obtém o certificado HTTPS automaticamente no primeiro arranque, desde que o DNS já aponte para o servidor. Para publicar uma nova versão:

```bash
git pull && docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
```

No repositório da gitmgf estes passos estão em scripts prontos (`deploy/setup-vps.sh` e `deploy/deploy.sh`) e descritos no `docs/RUNBOOK.md`. **Leia sempre um script antes de o correr como root.**

## 8. Opcional: email

Para enviar códigos de confirmação e notificações, usei o [Brevo](https://www.brevo.com) (SMTP, plano gratuito chega para começar) e, para receber emails em `contacto@` sem ter caixa de correio própria, o encaminhamento de email gratuito da Cloudflare. Dois erros que me apareceram: `535 Authentication failed` (era preciso a *chave SMTP*, não a chave da API) e `525 Unauthorized IP address` (o Brevo bloqueia IPs novos até os autorizar em *Security → Authorised IPs*).

## O que aprendi

- **Os documentos são o trabalho mais importante.** Um PRD claro poupa horas de correções. Quanto mais concretos os critérios de aceitação, melhor o resultado.
- **O Claude escreve; a responsabilidade é sua.** Rever o que é feito, sobretudo segurança, privacidade e textos legais. Numa ferramenta clínica, isto não é opcional.
- **Problemas de produção são quase sempre configuração.** Os meus erros 521 e 525 da Cloudflare eram variáveis em falta no `.env` e o certificado ainda a ser emitido, não erros no código.
- **Começar pequeno.** Um servidor de 5 € aguenta muito mais do que se pensa com SQLite e uma aplicação simples.

## Resumo de custos

| | Custo aproximado |
|---|---|
| Claude Pro (inclui o Claude Code) | ≈ 20 US$/mês (≈ 17 US$/mês com pagamento anual) |
| VPS na UE | ≈ 5–8 €/mês |
| Domínio `.com` | ≈ 10–12 US$/ano |
| Email (Brevo, plano gratuito) e Cloudflare | 0 € |

Se construir uma ferramenta útil para a prática clínica com este método, [partilhe-a na gitmgf](/me/tools/new).
