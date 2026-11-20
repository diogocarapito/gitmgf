---
subject: New suggestion for “{{ title }}”
---
Hello {{ name }},

{{ sender }} sent a suggestion for your tool “{{ title }}”.

Type: {{ kind }}

{{ message }}

{% if allow_reply %}You can reply directly to this email: your reply goes to the person who sent the suggestion.{% else %}The sender didn't share their email, so you can't reply here.{% endif %}

See all suggestions: {{ link }}
