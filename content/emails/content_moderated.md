---
subject: {% if hidden %}{% if is_comment %}Comentário ocultado{% else %}Colaboração ocultada{% endif %}{% else %}{% if is_comment %}Comentário visível novamente{% else %}Colaboração visível novamente{% endif %}{% endif %}: {{ title }}
---
Olá,

{% if hidden %}Medida: {% if is_comment %}o teu comentário em «{{ title }}» foi ocultado. Deixou de estar visível ao público.{% else %}a tua colaboração «{{ title }}» foi ocultada. Deixou de estar visível ao público.{% endif %}
{% if excerpt %}
Comentário:
{{ excerpt }}
{% endif %}
Motivo e factos:
{{ reason }}

A decisão foi tomada por um moderador, na sequência de uma denúncia ou de uma verificação da equipa.

{% include "_statement.md" %}{% else %}{% if is_comment %}O teu comentário em «{{ title }}» voltou a estar visível ao público.{% else %}A tua colaboração «{{ title }}» voltou a estar visível ao público.{% endif %}{% endif %}
