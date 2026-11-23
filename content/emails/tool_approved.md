---
subject: Ferramenta publicada: {{ title }}
---
Olá,

A ficha «{{ title }}» foi aprovada e já está publicada:
{{ base_url }}{{ lang_prefix }}/t/{{ slug }}
{% if checklist %}

Pontos verificados pelo moderador:
{{ checklist }}
{% endif %}{% if rejected_claims %}

Algumas certificações declaradas não foram aprovadas e não aparecem na ficha:
{{ rejected_claims }}

Podes corrigi-las editando a ficha; as alterações voltam a ser revistas.
{% endif %}
{% if suggestions %}

Sugestões do moderador (não impedem a publicação):
{{ suggestions }}
{% endif %}

Obrigado por contribuíres para a comunidade.
