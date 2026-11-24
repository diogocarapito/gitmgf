---
subject: {% if lifted %}Restrição levantada na tua conta{% else %}Restrição na tua conta gitmgf{% endif %}
---
Olá {{ name }},

{% if lifted %}{% if kind == "publish" %}A tua conta voltou a poder publicar ferramentas e colaborações.{% else %}A tua conta voltou a poder comentar e reagir.{% endif %}
{% else %}Medida: {% if kind == "publish" %}a tua conta deixou de poder publicar ferramentas e colaborações. As ferramentas já publicadas mantêm-se.{% else %}a tua conta deixou de poder comentar e reagir. Os comentários já publicados mantêm-se, salvo os que forem ocultados.{% endif %}

Motivo e factos:
{{ reason }}

A decisão foi tomada por um moderador.

{% include "_statement.md" %}{% endif %}
