---
subject: Tool published: {{ title }}
---
Hello,

The listing “{{ title }}” was approved and is now published:
{{ base_url }}{{ lang_prefix }}/t/{{ slug }}
{% if checklist %}

Checked by the moderator:
{{ checklist }}
{% endif %}{% if rejected_claims %}

Some declared certifications were not approved and don't appear on the listing:
{{ rejected_claims }}

You can fix them by editing the listing; the changes will be reviewed again.
{% endif %}
{% if suggestions %}

Suggestions from the moderator (they don't block publication):
{{ suggestions }}
{% endif %}

Thank you for contributing to the community.
