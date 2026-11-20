---
subject: {% if returned_to_draft %}Alterações pedidas: {{ title }}{% else %}Submissão não aprovada: {{ title }}{% endif %}
---
Olá,

{% if returned_to_draft %}Medida: a ficha «{{ title }}» não foi publicada e voltou a rascunho, para que a possa corrigir.{% else %}Medida: a ficha «{{ title }}» não foi aprovada para publicação.{% endif %}

Motivo e factos:
{{ reason }}
{% if checklist %}

Lista de verificação da revisão (✓ cumprido, ✗ por cumprir):
{{ checklist }}
{% endif %}
A decisão foi tomada por um moderador (não por meios automáticos).

{% include "_statement.md" %}

Pode editar a ficha e submetê-la novamente:
{{ base_url }}{{ lang_prefix }}/me/tools/{{ tool_id }}/edit
