---
subject: Decisão sobre a sua denúncia #{{ report_id }}
---
Olá,

{% if resolved %}Analisámos a sua denúncia sobre «{{ title }}» e tomámos medidas.{% else %}Analisámos a sua denúncia sobre «{{ title }}» e concluímos que não é necessária nenhuma medida.{% endif %}
{% if note %}

Nota da moderação:
{{ note }}
{% endif %}

Pode contestar esta decisão no prazo de 6 meses, respondendo a este email.
