---
subject: Tool hidden: {{ title }}
---
Hello,

Measure: the listing “{{ title }}” was hidden. It is no longer visible to the public or shown in search.

Reason and facts:
{{ reason }}

{% if automatic %}This measure was applied automatically, by automated means, after several reports of dangerous content or security problems, while a moderator reviews the case.{% else %}The decision was made by a moderator, following a report or a check by the team.{% endif %}

{% include "_statement_en.md" %}
