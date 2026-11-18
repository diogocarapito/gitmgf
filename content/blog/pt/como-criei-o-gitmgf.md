---
title: "Como criei o gitmgf em poucas horas com o Claude Pro e o Claude Code"
date: 2026-11-18
author: Diogo Carapito
summary: "Da ideia a um MVP em produção em poucas horas: PRD e especificação técnica no Claude, design e logótipo com artefactos, código com o Claude Code, e publicação num VPS europeu com domínio próprio. Com modelos de PRD e TECH_SPEC para copiar."
---

O gitmgf passou de ideia a site público em poucas horas de trabalho. Era esse o objetivo: construir um **MVP** (produto mínimo viável), a versão mais simples que já resolve o problema, e pô-lo no ar depressa. Não escrevi o código à mão: escrevi o que queria, revi o que o Claude propunha e tomei as decisões.

**Pôr uma ferramenta no ar, mesmo básica, é o passo mais importante.** Uma ferramenta simples que existe e que os colegas podem usar vale mais do que uma ferramenta perfeita que nunca sai do computador. É com utilizadores reais que se percebe o que falta, o que sobra e o que vale a pena melhorar. O resto pode vir depois, versão a versão.

Este artigo descreve o processo, passo a passo, para quem quiser fazer o mesmo com uma ferramenta para a sua prática clínica. No fim há [modelos de PRD e TECH_SPEC](#modelos-para-copiar) para copiar.

**O que é preciso:** uma subscrição do Claude Pro (inclui o Claude Code), uma conta no GitHub, um domínio e um servidor virtual (VPS). O Claude Pro só é necessário enquanto se constrói; **para manter o site no ar, o custo é apenas o do servidor (≈ 5–8 €/mês) e do domínio (≈ 10–12 US$/ano)**.

## 1. Escrever o PRD e a especificação técnica no Claude

Tudo começa num chat novo em [claude.ai](https://claude.ai) (botão **+ Novo chat**). O objetivo desta fase é chegar a dois documentos:

- **`PRD.md`** (*Product Requirements Document*): o quê e porquê. Para quem é, que problemas resolve, que funcionalidades tem o MVP, o que fica para depois, e os critérios de aceitação de cada funcionalidade. Deve conseguir ser lido por qualquer pessoa, sem conhecimentos técnicos.
- **`TECH_SPEC.md`**: o como. Tecnologias, modelo de dados, rotas, segurança, privacidade, testes e um plano por etapas (*milestones*), cada uma com uma "definição de concluído". É o guia que o Claude Code segue para escrever o código.

O que funcionou melhor foi pedir ao Claude que me entrevistasse antes de escrever:

> Quero criar um portal onde médicos de família partilham ferramentas digitais que criaram para a prática clínica. Faz-me perguntas, uma de cada vez, até teres informação suficiente. Depois escreve um `PRD.md` com objetivos, utilizadores, funcionalidades do MVP com critérios de aceitação, fora de âmbito e questões em aberto.

Depois, no mesmo chat:

> Com base no PRD, escreve um `TECH_SPEC.md` para um MVP simples de manter por uma pessoa: Python, FastAPI, SQLite, sem frameworks de frontend, alojado num VPS na UE com Docker. Inclui modelo de dados, segurança, RGPD, testes e milestones com definição de concluído.

Se preferir partir de uma estrutura, cole no chat os [modelos no fim do artigo](#modelos-para-copiar) e peça ao Claude que os preencha consigo.

Vale a pena ler tudo com calma e corrigir o que não corresponde ao que quer: estes dois ficheiros são o "contrato" que o Claude Code vai seguir. Aproveitei também para gerar um **`CLAUDE.md`** (convenções do projeto: comandos, regras de código, vocabulário em português europeu) e rascunhos dos textos legais (termos, privacidade). **Os textos legais gerados são apenas um ponto de partida e devem ser revistos por quem perceba do assunto.**

## 2. Design e logótipo com artefactos

Os artefactos do Claude mostram o resultado ao lado do chat, o que é ótimo para design. Pedi:

> Cria um mockup em HTML de uma página só com o sistema visual do gitmgf: paleta, tipografia, botões, cartões de ferramentas, página inicial, pesquisa e página de uma ferramenta, em modo claro e escuro, pensado primeiro para telemóvel.

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

**Antes de tornar público:** confirmar que o `.env` (palavras-passe, chaves) está no `.gitignore` e que nenhum segredo foi para o histórico. O código do gitmgf está em [github.com/diogocarapito/gitmgf](https://github.com/diogocarapito/gitmgf).

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

No gitmgf, o Caddy (servidor web) obtém o certificado HTTPS automaticamente no primeiro arranque, desde que o DNS já aponte para o servidor. Para publicar uma nova versão:

```bash
git pull && docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
```

No repositório do gitmgf estes passos estão em scripts prontos (`deploy/setup-vps.sh` e `deploy/deploy.sh`) e descritos no `docs/RUNBOOK.md`. **Leia sempre um script antes de o correr como root.**

## 8. Opcional: email

Para enviar códigos de confirmação e notificações, usei o [Brevo](https://www.brevo.com) (SMTP, plano gratuito chega para começar) e, para receber emails em `contacto@` sem ter caixa de correio própria, o encaminhamento de email gratuito da Cloudflare. Dois erros que me apareceram: `535 Authentication failed` (era preciso a *chave SMTP*, não a chave da API) e `525 Unauthorized IP address` (o Brevo bloqueia IPs novos até os autorizar em *Security → Authorised IPs*).

## O que aprendi

- **Os documentos são o trabalho mais importante.** Um PRD claro poupa horas de correções. Quanto mais concretos os critérios de aceitação, melhor o resultado.
- **Publicar cedo.** A primeira versão não tem de ser completa; tem de funcionar e estar no ar. As melhores ideias de melhoria vieram depois de o site existir.
- **O Claude escreve; a responsabilidade é sua.** Rever o que é feito, sobretudo segurança, privacidade e textos legais. Numa ferramenta clínica, isto não é opcional.
- **Problemas de produção são quase sempre configuração.** Os meus erros 521 e 525 da Cloudflare eram variáveis em falta no `.env` e o certificado ainda a ser emitido, não erros no código.
- **Começar pequeno.** Um servidor de 5 € aguenta muito mais do que se pensa com SQLite e uma aplicação simples.

## Resumo de custos

**Para construir** (só enquanto desenvolve):

| | Custo aproximado |
|---|---|
| Claude Pro (inclui o Claude Code) | ≈ 20 US$/mês (≈ 17 US$/mês com pagamento anual) |

**Para manter no ar:**

| | Custo aproximado |
|---|---|
| VPS na UE | ≈ 5–8 €/mês |
| Domínio `.com` | ≈ 10–12 US$/ano |
| Email (Brevo, plano gratuito) e Cloudflare | 0 € |

## Modelos para copiar

Estes modelos seguem a estrutura dos documentos do gitmgf, simplificada. Não é preciso preencher tudo: para uma ferramenta pequena, meia página por documento chega. O importante é que o PRD diga **o que** e **para quem**, e que o TECH_SPEC diga **como** e **por que ordem**.

### Modelo de PRD

```markdown
# <Nome da ferramenta> — PRD (Documento de Requisitos do Produto)

## 1. Resumo
Uma ou duas frases: o que é, para quem e porque é útil.

## 2. Problema
O que corre mal hoje? Como se resolve atualmente e quanto custa
(tempo, erros, frustração)?

## 3. Objetivos e não-objetivos
- Objetivos do MVP: 3 a 5, mensuráveis se possível.
- Não-objetivos: o que fica de fora de propósito.

## 4. Utilizadores
Quem usa, em que contexto (consulta, domicílio, telemóvel, computador
do centro de saúde) e com que à-vontade com tecnologia. 2 a 3 perfis curtos.

## 5. Funcionalidades do MVP
Lista curta, por prioridade (Obrigatório / Desejável).

## 6. Requisitos funcionais
Para cada funcionalidade:
### F1 — <nome>
- O que faz, regras e casos-limite.
- Critérios de aceitação: "Um utilizador consegue … e vê …".

## 7. Requisitos não funcionais
Desempenho, acessibilidade, idiomas, dispositivos, disponibilidade.

## 8. Privacidade e regulamentação
Que dados pessoais trata? Há dados de utentes? Pode ser um dispositivo
médico? (Confirmar com quem saiba antes de lançar.)

## 9. Métricas de sucesso
Como saber, ao fim de 3 a 6 meses, se resultou.

## 10. Plano de lançamento
MVP → teste com poucos colegas → abertura ao público.

## 11. Para depois do MVP
Boas ideias que não entram agora.

## 12. Questões em aberto
Decisões por tomar, cada uma com a opção por defeito.
```

### Modelo de TECH_SPEC

```markdown
# <Nome da ferramenta> — Especificação técnica

## 1. Arquitetura
Esquema simples: navegador → servidor web → aplicação → base de dados.
Onde corre (computador local, VPS, serviço na nuvem).

## 2. Tecnologias
Linguagem, framework, base de dados e bibliotecas principais, com versões.
O que NÃO usar (para manter o projeto simples).

## 3. Estrutura do repositório
Pastas e o que vive em cada uma.

## 4. Configuração
Variáveis de ambiente (.env): quais são obrigatórias e quais são secretas.

## 5. Modelo de dados
Tabelas, campos e relações. Estados e transições
(ex.: rascunho → pendente → publicado).

## 6. Autenticação e permissões
Como se inicia sessão, que papéis existem (utilizador, moderador,
administrador) e quem pode fazer o quê.

## 7. Páginas e rotas
Lista de páginas e ações: o que mostram, que dados recebem, quem lhes acede.

## 8. Regras e fluxos principais
Os fluxos importantes, passo a passo (ex.: submeter, rever, publicar).

## 9. Segurança e privacidade
Lista de verificação: HTTPS, palavras-passe, proteção de formulários,
validação de dados, registos sem dados pessoais, prazos de conservação.

## 10. Emails e tarefas agendadas
O que é enviado e quando; que tarefas correm em segundo plano.

## 11. Testes
O que tem de estar sempre testado (permissões, fluxos principais).

## 12. Deploy
Servidor, Docker, domínio, HTTPS, cópias de segurança e como publicar
uma nova versão.

## 13. Plano de implementação
Etapas por ordem, cada uma com uma "definição de concluído".
Ex.: 1. Base e páginas estáticas · 2. Contas · 3. Funcionalidade principal ·
4. Pesquisa · 5. Segurança e deploy.

## 14. Registo de decisões
Decisões tomadas e porquê (pode viver num ficheiro à parte, DECISIONS.md).
```

## Agora é a sua vez

Quase todos os clínicos têm uma ideia guardada: uma calculadora que faz falta na consulta, um protocolo que podia ser um fluxograma interativo, uma lista de verificação para o Internato, uma forma mais rápida de fazer aquela tarefa repetitiva. Até há pouco tempo, passar dessa ideia a uma ferramenta exigia saber programar ou pagar a quem soubesse. Hoje, a distância é de poucas horas e de uma boa descrição do problema.

Escolha uma ideia pequena, escreva o problema, peça ao Claude que o entreviste e publique a primeira versão, mesmo simples. Os colegas que a usarem vão dizer-lhe o que melhorar. E quando estiver no ar, [partilhe-a no gitmgf](/me/tools/new).
