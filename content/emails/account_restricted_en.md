---
subject: {% if lifted %}Restriction lifted on your account{% else %}Restriction on your gitmgf account{% endif %}
---
Hello {{ name }},

{% if lifted %}{% if kind == "publish" %}Your account can publish tools and collaboration posts again.{% else %}Your account can comment and react again.{% endif %}
{% else %}Measure: {% if kind == "publish" %}your account can no longer publish tools or collaboration posts. Tools already published stay up.{% else %}your account can no longer comment or react. Comments already published stay up, unless they are hidden.{% endif %}

Reason and facts:
{{ reason }}

The decision was taken by a moderator.

{% include "_statement_en.md" %}{% endif %}
