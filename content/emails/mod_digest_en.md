---
subject: gitmgf: {{ total }} items awaiting moderation
---
Hello,

New submissions: {{ new }}
Edits: {{ edits }}
Open reports: {{ reports }}
{% if oldest %}Oldest item: {{ oldest }}{% endif %}

{{ base_url }}{{ lang_prefix }}/mod
