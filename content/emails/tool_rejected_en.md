---
subject: {% if returned_to_draft %}Changes requested: {{ title }}{% else %}Submission not approved: {{ title }}{% endif %}
---
Hello,

{% if returned_to_draft %}Measure: the listing “{{ title }}” has not been validated yet and went back to draft so you can fix it. It stays visible, marked “In review”, until you submit it again.{% else %}Measure: the listing “{{ title }}” was not approved and is no longer visible to the public.{% endif %}

Reason and facts:
{{ reason }}
{% if checklist %}

Review checklist (✓ met, ✗ not met):
{{ checklist }}
{% endif %}
The decision was made by a moderator (not by automated means).

{% include "_statement_en.md" %}

You can edit the listing and submit it again:
{{ base_url }}{{ lang_prefix }}/me/tools/{{ tool_id }}/edit
