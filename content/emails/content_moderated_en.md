---
subject: {% if hidden %}{% if is_comment %}Comment hidden{% else %}Collaboration post hidden{% endif %}{% else %}{% if is_comment %}Comment visible again{% else %}Collaboration post visible again{% endif %}{% endif %}: {{ title }}
---
Hello,

{% if hidden %}Measure: {% if is_comment %}your comment on “{{ title }}” has been hidden. It is no longer visible to the public.{% else %}your collaboration post “{{ title }}” has been hidden. It is no longer visible to the public.{% endif %}
{% if excerpt %}
Comment:
{{ excerpt }}
{% endif %}
Reason and facts:
{{ reason }}

The decision was taken by a moderator, following a report or a check by the team.

{% include "_statement_en.md" %}{% else %}{% if is_comment %}Your comment on “{{ title }}” is visible to the public again.{% else %}Your collaboration post “{{ title }}” is visible to the public again.{% endif %}{% endif %}
