---
subject: Decision on your report #{{ report_id }}
---
Hello,

{% if resolved %}We reviewed your report about “{{ title }}” and took action.{% else %}We reviewed your report about “{{ title }}” and concluded that no action is needed.{% endif %}
{% if note %}

Moderation note:
{{ note }}
{% endif %}

You can appeal this decision within 6 months by replying to this email.
