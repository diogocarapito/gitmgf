---
subject: Nova sugestão para «{{ title }}»
---
Olá {{ name }},

{{ sender }} enviou uma sugestão para a tua ferramenta «{{ title }}».

Tipo: {{ kind }}

{{ message }}

{% if allow_reply %}Podes responder diretamente a este email: a resposta vai para quem enviou a sugestão.{% else %}Quem enviou a sugestão não partilhou o email, por isso não é possível responder por aqui.{% endif %}

Ver todas as sugestões: {{ link }}
