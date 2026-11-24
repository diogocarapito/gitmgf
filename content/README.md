# Textos do site

Os textos editoriais do gitmgf estão aqui, em Markdown, para poderem ser editados sem mexer no código.
Este ficheiro (e `legal/NOTES.md`) não é publicado.

## Regra

- Cada página tem uma pasta: `home/`, `about/`, `legal/`, `blog/`, `emails/`, `categories/`...
- Cada texto é um ficheiro `.md` em português (a versão que prevalece) com a tradução inglesa ao lado, com o mesmo nome e `_en` no fim: `home/hero.md` e `home/hero_en.md`.
- Se faltar o `_en.md`, a versão inglesa do site mostra o texto em português, mas os testes (CI) falham: acrescente sempre a tradução.
- As alterações aparecem no site no próximo deploy.

## Formato

```markdown
---
title: Criar
icon: lightbulb
---
Uma calculadora, um script ou uma folha de cálculo que resolve um problema real da consulta.
```

- Entre as linhas `---` ficam campos curtos, um por linha (`campo: valor`). Tudo o que vem depois dos primeiros dois pontos é o valor; não são precisas aspas. Não mude os nomes dos campos (`title`, `icon`, `eyebrow`, `empty`...): o modelo da página procura-os por esse nome. `icon` é o nome de um ícone de `app/static/icons/sprite.svg`.
- Depois das linhas `---` vem o texto, em Markdown: `**negrito**`, `*itálico*`, `[ligação](/p/guidelines)`, listas, parágrafos separados por uma linha em branco.
- Nas versões inglesas, as ligações internas levam `/en` à frente: `[Submission guidelines](/en/p/guidelines)`.
- `{{ name }}` (entre chavetas duplas) é um valor preenchido pelo site, como o nome do autor. Pode mudá-lo de sítio na frase, mas mantenha-o escrito igual.

## Pastas

| Pasta | O que tem |
|---|---|
| `home/` | Página inicial: `hero` (destaque no topo), `featured`, `newest`, `how-it-works` + `step-1..3`, `cta` |
| `about/`, `contact/` | Páginas Sobre e Contacto (`/p/about`, `/p/contact`) |
| `legal/` | Termos, Privacidade, Aviso Legal e Normas de Submissão. `[[CHAVE]]` são dados preenchidos nas definições do site (ver `legal/NOTES.md`). Mudanças que obriguem a nova aceitação: atualizar `version` em `legal/terms.md` e a definição `terms.current_version` |
| `blog/` | Um artigo por ficheiro: `<endereço>.md` + `<endereço>_en.md`, com `title`, `date`, `author`, `summary` (e `draft: true` para esconder). `_intro.md` é o texto do topo da página do blog |
| `emails/` | Emails enviados pelo site (ver abaixo) |
| `notice/` | Aviso mostrado na primeira visita (responsabilidade dos autores), com `title` e `button` |
| `colabs/` | Página Colaborações: `intro` (título e texto do topo) e `guidance` (conselhos no formulário) |
| `comments/` | `intro`: texto por cima dos comentários na página de cada ferramenta |
| `categories/`, `report/`, `suggest/`, `notifications/`, `stars/`, `my-tools/`, `submit/`, `onboarding/`, `delete-account/` | Textos de introdução dessas páginas |

Botões, menus, campos de formulário e mensagens de erro continuam no catálogo de traduções (`app/locales`), porque estão ligados ao código.

## Emails

Os emails são texto simples (sem Markdown). O campo `subject` é o assunto. Além de `{{ valor }}`, podem ter partes condicionais:

```
{% if suggestions %}
Sugestões do moderador (não impedem a publicação):
{{ suggestions }}
{% endif %}
```

Mantenha as linhas `{% ... %}` como estão e altere apenas o texto à volta. `{% include "_statement.md" %}` insere o parágrafo comum sobre regras e contestação (`_statement.md` / `_statement_en.md`). Em desenvolvimento, os emails enviados aparecem em `/dev/emails`.
