---
subject: gitmgf: {{ total }} itens à espera de moderação
---
Olá,

Novas submissões: {{ new }}
Alterações: {{ edits }}
Denúncias abertas: {{ reports }}
{% if oldest %}Item mais antigo: {{ oldest }}{% endif %}

{{ base_url }}{{ lang_prefix }}/mod
