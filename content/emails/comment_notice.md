---
subject: {% if kind == "comment_reply" %}{{ actor }} respondeu-te em «{{ title }}»{% elif kind == "comment_mention" %}{{ actor }} mencionou-te em «{{ title }}»{% else %}Novo comentário em «{{ title }}»{% endif %}
---
Olá {{ name }},

{% if kind == "comment_reply" %}{{ actor }} respondeu ao teu comentário em «{{ title }}»:{% elif kind == "comment_mention" %}{{ actor }} mencionou-te num comentário em «{{ title }}»:{% else %}{{ actor }} comentou «{{ title }}»:{% endif %}

{{ excerpt }}

Ver e responder: {{ link }}

Não queres receber estes emails? Desativa-os em Definições: {{ settings_link }}
