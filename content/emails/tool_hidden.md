---
subject: Ferramenta ocultada: {{ title }}
---
Olá,

Medida: a ficha «{{ title }}» foi ocultada. Deixou de estar visível ao público e de aparecer na pesquisa.

Motivo e factos:
{{ reason }}

{% if automatic %}Esta medida foi aplicada automaticamente, por meios automáticos, depois de várias denúncias de conteúdo perigoso ou de problemas de segurança, enquanto um moderador analisa o caso.{% else %}A decisão foi tomada por um moderador, na sequência de uma denúncia ou de uma verificação da equipa.{% endif %}

{% include "_statement.md" %}
