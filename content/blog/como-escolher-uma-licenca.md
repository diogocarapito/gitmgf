---
title: Que licença escolher para a minha ferramenta?
date: 2026-11-23
author: Diogo Carapito
summary: O que é uma licença, porque é que uma ferramenta sem licença não pode ser usada à vontade, e que licença escolher em casos simples: uma calculadora, uma webapp, uma folha de cálculo, um protocolo ou uma ferramenta de código fechado.
---

Quando submetes uma ferramenta no gitmgf, um dos campos obrigatórios é a **licença**. Para muitos clínicos é a pergunta mais estranha do formulário: o que interessa isso, se só quero que os colegas usem a ferramenta?

Interessa mais do que parece. A licença é o que diz aos outros **o que podem fazer** com o que criaste: usar, copiar, adaptar, partilhar, vender. Este artigo explica o essencial e propõe uma escolha para os casos mais comuns.

*Nota: este artigo é informativo e não é aconselhamento jurídico. Em caso de dúvida, sobretudo se houver uma instituição ou uma empresa envolvida, fala com quem perceba do assunto.*

## Sem licença, ninguém pode usar à vontade

Pela lei dos direitos de autor, quem cria um programa, uma folha de cálculo ou um texto fica automaticamente com todos os direitos sobre ele. Se não disseres nada, **os outros não podem legalmente copiar, adaptar nem redistribuir** o que fizeste, mesmo que o código esteja num repositório público no GitHub.

Ou seja: pôr o código à vista não é o mesmo que o tornar aberto. Para que um colega possa adaptar a tua calculadora à realidade da USF dele, ou corrigir um erro e devolver a correção, tens de lhe dar essa autorização. É isso que faz uma licença.

## As famílias de licenças

Há centenas de licenças, mas quase todas cabem numa destas famílias:

| Família | Em poucas palavras | Exemplos |
|---|---|---|
| **Permissivas** | Qualquer pessoa pode usar, alterar e redistribuir, até em produtos fechados ou comerciais. Só tem de manter o aviso de autoria. | MIT, Apache-2.0, BSD, ISC |
| **Copyleft** | Pode usar e alterar, mas quem distribuir uma versão alterada tem de a partilhar com a mesma licença. As melhorias ficam abertas. | GPL-3.0, AGPL-3.0, EUPL-1.2, MPL-2.0, LGPL-3.0 |
| **Domínio público** | Abdicas de (quase) todos os direitos. Qualquer pessoa faz o que quiser, sem sequer ter de te citar. | CC0-1.0, Unlicense |
| **Creative Commons** | Pensadas para conteúdos (textos, imagens, documentos), não para código. | CC BY, CC BY-SA, CC BY-NC |
| **Proprietária** | Guardas todos os direitos. Decides caso a caso o que os outros podem fazer. | "Todos os direitos reservados" |

No gitmgf, uma ficha recebe o selo **Open source** quando tem uma licença de código aberto aprovada pela [Open Source Initiative](https://opensource.org/licenses) (as permissivas, as copyleft e a Unlicense da lista do formulário) e um repositório público.

## As licenças do formulário, uma a uma

Estas são todas as opções que encontras no formulário de submissão, agrupadas por família.

| Licença | Família | O que significa |
|---|---|---|
| **MIT** | Permissiva | A mais usada em projetos pequenos: qualquer pessoa pode usar, copiar, alterar, vender e incluir o código noutros projetos, abertos ou fechados. A única obrigação é manter o aviso de autoria e o texto da licença. Como quase todas as licenças abertas, diz que o software é fornecido "tal como está", sem garantias. |
| **ISC** | Permissiva | Na prática, equivale à MIT, com um texto ainda mais curto. Dá as mesmas liberdades e pede o mesmo: manter o aviso de autoria. É comum em alguns ecossistemas, como o do JavaScript, mas menos conhecida fora deles. |
| **BSD-2-Clause** | Permissiva | Muito semelhante à MIT: uso livre, desde que se mantenha o aviso de autoria no código e na documentação de versões distribuídas. A diferença em relação à MIT é sobretudo de redação. É uma escolha comum em projetos académicos. |
| **BSD-3-Clause** | Permissiva | Igual à BSD-2-Clause, com uma cláusula a mais: o teu nome (ou o da tua instituição) não pode ser usado para promover produtos derivados sem autorização. Útil quando não queres que uma versão alterada pareça ter o teu aval. |
| **Apache-2.0** | Permissiva | Dá as mesmas liberdades da MIT, mas inclui uma autorização explícita de patentes, que termina para quem processar outros por violação de patentes relacionadas com o código. Obriga a indicar as alterações feitas nos ficheiros modificados e a manter um eventual ficheiro `NOTICE`. É compatível com a GPL-3.0, mas não com a GPL-2.0. |
| **GPL-3.0** | Copyleft forte | Qualquer pessoa pode usar e alterar, mas quem distribuir a ferramenta, alterada ou combinada com outro código, tem de o fazer com a GPL-3.0 e disponibilizar o código-fonte. Garante que as melhorias continuam abertas. Não se aplica a quem apenas põe o programa a correr num servidor (para isso existe a AGPL). |
| **GPL-2.0** | Copyleft forte | A versão anterior da GPL, de 1991, ainda usada em projetos conhecidos como o Linux. A ideia é a mesma da GPL-3.0, mas não trata patentes e é incompatível com a Apache-2.0 e com a própria GPL-3.0. Para um projeto novo, prefere a GPL-3.0, salvo se dependeres de código que só existe em GPL-2.0. |
| **AGPL-3.0** | Copyleft forte | É a GPL-3.0 com uma regra extra para a web: quem oferecer uma versão alterada através de uma rede (por exemplo, uma webapp) tem de dar aos utilizadores acesso ao código dessa versão. É a licença que garante que melhorias numa webapp continuam abertas. Algumas empresas evitam-na por isso mesmo. |
| **EUPL-1.2** | Copyleft | A licença de código aberto da União Europeia, com o mesmo valor jurídico em todas as línguas oficiais da UE, incluindo o português. Tal como a AGPL, aplica-se também a serviços disponibilizados online. Tem uma cláusula de compatibilidade que permite combinar o código com projetos em GPL, AGPL, LGPL, MPL e outras. |
| **LGPL-3.0** | Copyleft fraco | Pensada para bibliotecas: programas que apenas usam a biblioteca podem ter qualquer licença, mesmo fechada. Mas quem alterar a própria biblioteca e a distribuir tem de partilhar essas alterações com a LGPL. Faz sentido se criaste um componente que queres ver usado por muitos, sem perder as melhorias feitas a ele. |
| **MPL-2.0** | Copyleft fraco | O copyleft aplica-se ficheiro a ficheiro: quem alterar um ficheiro com MPL tem de partilhar esse ficheiro, mas pode juntá-lo a outros ficheiros com qualquer licença, incluindo fechada. É um meio-termo entre a MIT e a GPL. É compatível com a GPL. |
| **Unlicense** | Domínio público | Declara a obra no domínio público: qualquer pessoa faz o que quiser, sem ter de te citar. Inclui uma licença permissiva de recurso para países onde a renúncia não é possível. Foi escrita a pensar na lei dos EUA e alguns juristas consideram-na menos sólida na Europa. |
| **CC0-1.0** | Domínio público | Renuncia a todos os direitos tanto quanto a lei permite e, onde não é possível, funciona como uma licença muito permissiva. É a escolha habitual para dados e tabelas que queres que circulem sem restrições. Não é aprovada pela OSI porque exclui expressamente as patentes, por isso a ficha não recebe o selo Open source. |
| **CC BY 4.0** | Creative Commons | Qualquer pessoa pode usar, partilhar e adaptar o conteúdo, mesmo para fins comerciais, desde que te cite, indique a licença e assinale as alterações. É a forma mais simples de partilhar um protocolo, um fluxograma, uma apresentação ou uma folha de cálculo simples. Não é pensada para código. |
| **CC BY-SA 4.0** | Creative Commons | Igual à CC BY, mas as versões adaptadas têm de ser partilhadas com a mesma licença: é o "copyleft" dos conteúdos. É a licença da Wikipédia. Boa escolha para materiais que queres ver melhorados em conjunto, como guias para o Internato. |
| **CC BY-NC 4.0** | Creative Commons | Qualquer pessoa pode usar e adaptar, citando-te, mas não para fins comerciais. O problema é definir o que é comercial: uma clínica privada ou uma formação paga, por exemplo, podem ficar numa zona cinzenta. Não é uma licença aberta e a ficha não recebe o selo Open source. |
| **CC BY-NC-SA 4.0** | Creative Commons | Junta as duas restrições anteriores: sem uso comercial e com as versões adaptadas obrigadas a manter a mesma licença. É a mais restritiva das Creative Commons desta lista. Tem os mesmos problemas de ambiguidade da CC BY-NC. |
| **Proprietária / código fechado** | Proprietária | Guardas todos os direitos e defines tu as regras, por exemplo em termos de utilização. Fechado não quer dizer pago: uma ferramenta gratuita pode ser proprietária. Os colegas podem usá-la, mas não a podem adaptar nem verificar como funciona. |
| **Desconhecida** | — | Usa só se não souberes mesmo qual é a licença. Na prática, sem licença aplicam-se todos os direitos de autor, por isso os colegas não podem adaptar nem redistribuir a ferramenta. Se a ferramenta é tua, escolhe uma licença: demora dois minutos. |

## Casos simples

### "Fiz uma calculadora e quero que qualquer pessoa a use e adapte, sem complicações"

**MIT.** É curta, conhecida e fácil de cumprir: qualquer pessoa pode usar, alterar e partilhar, desde que mantenha o teu nome e o texto da licença. É a escolha mais comum para ferramentas pequenas e uma boa opção por defeito.

### "Quero que as melhorias feitas por outros também fiquem abertas"

**GPL-3.0.** Quem distribuir uma versão alterada da tua ferramenta tem de a disponibilizar com a mesma licença e com o código. Assim, se um colega melhorar a tua ferramenta e a partilhar, a melhoria volta a estar ao alcance de todos.

### "É uma webapp que corre num servidor"

**AGPL-3.0.** A GPL só obriga a partilhar quando se *distribui* o programa; quem o põe a correr num servidor e o disponibiliza na web não está a distribuí-lo. A AGPL fecha essa porta: quem oferecer uma versão alterada através da internet tem de partilhar o código. Se não te importas que alguém faça uma versão fechada, a MIT continua a ser válida.

### "Trabalho no SNS e prefiro uma licença europeia, em português"

**EUPL-1.2.** É a licença de código aberto da União Europeia, com versões com o mesmo valor jurídico em todas as línguas oficiais da UE, incluindo o português. É copyleft, aplica-se também a serviços disponibilizados online e é compatível com outras licenças conhecidas, como a GPL e a MPL. Uma boa escolha para ferramentas ligadas a instituições públicas.

### "Uma empresa pode vir a usar o código e preocupa-me a questão das patentes"

**Apache-2.0.** É permissiva como a MIT, mas inclui uma autorização explícita de patentes e regras mais claras sobre contribuições. É mais longa, mas dá mais segurança jurídica em projetos maiores.

### "Não é código: é uma folha de cálculo, um protocolo, um fluxograma ou material para o Internato"

**CC BY 4.0** (qualquer pessoa pode usar e adaptar, desde que te cite) ou **CC BY-SA 4.0** (o mesmo, mas as versões adaptadas têm de manter a licença). As licenças Creative Commons foram feitas para conteúdos e a própria Creative Commons [desaconselha usá-las para software](https://creativecommons.org/faq/). Se a folha de cálculo tiver macros ou scripts com algum peso, trata essa parte como código (MIT ou GPL, por exemplo).

### "Não quero que ninguém ganhe dinheiro com isto"

**CC BY-NC 4.0** ou **CC BY-NC-SA 4.0**, com duas ressalvas. Primeiro, a cláusula "não comercial" é mais ambígua do que parece: uma clínica privada que usa a ferramenta na consulta está a fazer uso comercial? Segundo, as licenças NC não são de código aberto, por isso a ficha não recebe o selo Open source. Antes de escolher, pergunta-te se o risco de alguém lucrar justifica afastar quem poderia ajudar. Muitas vezes, uma licença copyleft (GPL ou AGPL) protege o que te preocupa sem estes inconvenientes.

### "Não quero saber de nada: façam o que quiserem"

**CC0-1.0** ou **Unlicense.** Abdicas dos direitos tanto quanto a lei permite. A CC0 está mais bem preparada para países, como Portugal, onde não é possível renunciar a todos os direitos de autor: nesses casos funciona como uma licença muito permissiva. Na prática, a MIT dá quase a mesma liberdade e garante que o teu nome continua associado ao trabalho.

### "Não quero partilhar o código"

**Proprietária / código fechado.** É uma escolha legítima e a ferramenta pode estar no gitmgf na mesma. Os colegas podem usá-la, mas não a podem adaptar nem verificar como faz os cálculos, e a ficha não recebe o selo Open source. Em saúde, poder ver como um cálculo é feito é uma vantagem real; vale a pena pesar isso.

## Resumo rápido

| Se queres… | Escolhe |
|---|---|
| A opção mais simples e livre, com o teu nome mantido | MIT |
| Que as versões alteradas continuem abertas | GPL-3.0 |
| O mesmo, numa webapp | AGPL-3.0 |
| Uma licença europeia, oficial em português | EUPL-1.2 |
| Proteção explícita em matéria de patentes | Apache-2.0 |
| Partilhar um documento, protocolo ou folha de cálculo simples | CC BY 4.0 |
| Abdicar de todos os direitos | CC0-1.0 |
| Manter o código fechado | Proprietária |

Se continuares indeciso, escolhe **MIT** para código e **CC BY 4.0** para conteúdos. Para comparar outras opções, o site [choosealicense.com](https://choosealicense.com) (do GitHub) e o [seletor da Creative Commons](https://creativecommons.org/chooser/) ajudam a decidir em poucos cliques.

## Como aplicar a licença

1. **No repositório:** cria um ficheiro chamado `LICENSE` na pasta principal. No GitHub, em **Add file → Create new file**, escreve `LICENSE` como nome e aparece o botão **Choose a license template**, que preenche o texto, o ano e o teu nome.
2. **Numa folha de cálculo ou documento:** acrescenta uma linha visível, por exemplo numa folha "Sobre" ou no rodapé: *"© 2026 Nome Apelido. Licença CC BY 4.0: https://creativecommons.org/licenses/by/4.0/deed.pt"*.
3. **No gitmgf:** escolhe a mesma licença no formulário da ficha. A moderação confirma que a licença indicada é coerente com o repositório, e a ficha mostra também a licença que o GitHub deteta.

## Antes de escolher, confirma três coisas

- **Quem é o dono?** Se criaste a ferramenta no exercício das tuas funções ou por encomenda, a lei portuguesa pode atribuir os direitos à entidade empregadora ou a quem encomendou, salvo acordo em contrário. Se a ferramenta nasceu dentro de uma ULS, de um projeto financiado ou de uma empresa, confirma primeiro quem pode decidir a licença.
- **O que usaste de outros?** Se a ferramenta inclui código, bibliotecas, escalas ou tabelas de terceiros, a tua licença tem de ser compatível com a deles. Por exemplo, se usas uma biblioteca GPL e distribuis o conjunto, a tua ferramenta também tem de ser GPL. Escalas clínicas publicadas podem ter direitos próprios; confirma antes de as reproduzir.
- **A licença não substitui o cuidado clínico.** Quase todas as licenças de código aberto dizem que o software é fornecido "tal como está", sem garantias. Isso limita a tua responsabilidade enquanto autor, mas não dispensa validar os cálculos, indicar as fontes e avisar os limites de uso. E não muda as regras sobre dispositivos médicos: se a ferramenta pode ser um dispositivo médico, isso decide-se pela finalidade, não pela licença.

## Posso mudar de ideias depois?

Sim, com limites. Se és o único autor, podes publicar as versões seguintes com outra licença. As versões que já partilhaste continuam com a licença original: quem as recebeu mantém esses direitos. Se outras pessoas já contribuíram com código, precisas do acordo delas para mudar a licença das partes que escreveram.

Por isso vale a pena pensar uns minutos agora. Mas não deixes que esta escolha atrase a publicação: uma ferramenta com licença MIT no ar é mais útil do que uma ferramenta perfeita à espera da licença ideal. Quando estiver pronta, [partilha-a no gitmgf](/me/tools/new).
