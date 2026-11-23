---
subject: Decisão sobre a tua denúncia #{{ report_id }}
---
Olá,

{% if resolved %}Analisámos a tua denúncia sobre «{{ title }}» e tomámos medidas.{% else %}Analisámos a tua denúncia sobre «{{ title }}» e concluímos que não é necessária nenhuma medida.{% endif %}
{% if note %}

Nota da moderação:
{{ note }}
{% endif %}

Podes contestar esta decisão no prazo de 6 meses, respondendo a este email.
