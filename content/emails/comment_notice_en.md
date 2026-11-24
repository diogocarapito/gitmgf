---
subject: {% if kind == "comment_reply" %}{{ actor }} replied to you on “{{ title }}”{% elif kind == "comment_mention" %}{{ actor }} mentioned you on “{{ title }}”{% else %}New comment on “{{ title }}”{% endif %}
---
Hello {{ name }},

{% if kind == "comment_reply" %}{{ actor }} replied to your comment on “{{ title }}”:{% elif kind == "comment_mention" %}{{ actor }} mentioned you in a comment on “{{ title }}”:{% else %}{{ actor }} commented on “{{ title }}”:{% endif %}

{{ excerpt }}

See and reply: {{ link }}

Don't want these emails? Turn them off in Settings: {{ settings_link }}
