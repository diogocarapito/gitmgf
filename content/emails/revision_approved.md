---
subject: Alteração aprovada: {{ title }}
---
Olá,

As alterações à ficha «{{ title }}» foram aprovadas e já estão publicadas:
{{ base_url }}{{ lang_prefix }}/t/{{ slug }}
{% if rejected_claims %}

Algumas certificações não foram aprovadas:
{{ rejected_claims }}
{% endif %}
{% if suggestions %}

Sugestões do moderador (não impedem a publicação):
{{ suggestions }}
{% endif %}
