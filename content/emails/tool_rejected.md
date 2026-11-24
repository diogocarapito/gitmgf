---
subject: {% if returned_to_draft %}Alterações pedidas: {{ title }}{% else %}Submissão não aprovada: {{ title }}{% endif %}
---
Olá,

{% if returned_to_draft %}Medida: a ficha «{{ title }}» ainda não foi validada e voltou a rascunho, para que a possas corrigir. Continua visível, com o aviso «Em revisão», até a submeteres de novo.{% else %}Medida: a ficha «{{ title }}» não foi aprovada e deixou de estar visível ao público.{% endif %}

Motivo e factos:
{{ reason }}
{% if checklist %}

Lista de verificação da revisão (✓ cumprido, ✗ por cumprir):
{{ checklist }}
{% endif %}
A decisão foi tomada por um moderador (não por meios automáticos).

{% include "_statement.md" %}

Podes editar a ficha e submetê-la novamente:
{{ base_url }}{{ lang_prefix }}/me/tools/{{ tool_id }}/edit
