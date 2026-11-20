---
subject: Edit approved: {{ title }}
---
Hello,

The changes to the listing “{{ title }}” were approved and are now published:
{{ base_url }}{{ lang_prefix }}/t/{{ slug }}
{% if rejected_claims %}

Some certifications were not approved:
{{ rejected_claims }}
{% endif %}
{% if suggestions %}

Suggestions from the moderator (they don't block publication):
{{ suggestions }}
{% endif %}
