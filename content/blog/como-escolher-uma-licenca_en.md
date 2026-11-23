---
title: Which licence should I choose for my tool?
date: 2026-11-23
author: Diogo Carapito
summary: What a licence is, why a tool without one can't be freely used, and which licence to pick in simple cases: a calculator, a web app, a spreadsheet, a protocol or a closed-source tool.
---

When you submit a tool to gitmgf, one of the required fields is the **licence**. For many clinicians it's the strangest question on the form: why does it matter, if all I want is for colleagues to use the tool?

It matters more than it seems. The licence is what tells others **what they may do** with what you made: use it, copy it, adapt it, share it, sell it. This article covers the essentials and suggests a choice for the most common cases.

*Note: this article is for information only and is not legal advice. If in doubt, especially when an institution or a company is involved, talk to someone who knows the subject.*

## Without a licence, nobody can use it freely

Under copyright law, whoever creates a program, a spreadsheet or a text automatically holds all rights to it. If you say nothing, **others may not legally copy, adapt or redistribute** what you made, even if the code sits in a public GitHub repository.

In other words: making the code visible is not the same as making it open. For a colleague to adapt your calculator to their own practice, or fix a bug and send the fix back, you have to give them permission. That's what a licence does.

## Licence families

There are hundreds of licences, but almost all of them fit one of these families:

| Family | In a few words | Examples |
|---|---|---|
| **Permissive** | Anyone may use, change and redistribute it, even in closed or commercial products. They just have to keep the copyright notice. | MIT, Apache-2.0, BSD, ISC |
| **Copyleft** | Anyone may use and change it, but whoever distributes a modified version must share it under the same licence. Improvements stay open. | GPL-3.0, AGPL-3.0, EUPL-1.2, MPL-2.0, LGPL-3.0 |
| **Public domain** | You give up (almost) all rights. Anyone can do anything, without even crediting you. | CC0-1.0, Unlicense |
| **Creative Commons** | Designed for content (texts, images, documents), not code. | CC BY, CC BY-SA, CC BY-NC |
| **Proprietary** | You keep all rights and decide case by case what others may do. | "All rights reserved" |

On gitmgf, a listing gets the **Open source** badge when it has an open source licence approved by the [Open Source Initiative](https://opensource.org/licenses) (the permissive and copyleft ones, plus the Unlicense, from the form's list) and a public repository.

## The licences on the form, one by one

These are all the options you'll find on the submission form, grouped by family.

| Licence | Family | What it means |
|---|---|---|
| **MIT** | Permissive | The most used licence for small projects: anyone may use, copy, change, sell and include the code in other projects, open or closed. The only obligation is to keep the copyright notice and the licence text. Like almost all open licences, it says the software is provided "as is", without warranty. |
| **ISC** | Permissive | In practice equivalent to MIT, with an even shorter text. It grants the same freedoms and asks the same: keep the copyright notice. It's common in some ecosystems, such as JavaScript, but less known outside them. |
| **BSD-2-Clause** | Permissive | Very similar to MIT: free use, as long as the copyright notice is kept in the code and in the documentation of distributed versions. The difference from MIT is mostly wording. It's a common choice in academic projects. |
| **BSD-3-Clause** | Permissive | The same as BSD-2-Clause, with one extra clause: your name (or your institution's) may not be used to promote derived products without permission. Useful when you don't want a modified version to look as if you endorse it. |
| **Apache-2.0** | Permissive | Grants the same freedoms as MIT, but includes an explicit patent grant, which ends for anyone who sues others over patents related to the code. It requires stating the changes made in modified files and keeping any `NOTICE` file. It's compatible with GPL-3.0 but not with GPL-2.0. |
| **GPL-3.0** | Strong copyleft | Anyone may use and change it, but whoever distributes the tool, modified or combined with other code, must do so under GPL-3.0 and make the source code available. It ensures improvements stay open. It doesn't apply to those who only run the program on a server (that's what the AGPL is for). |
| **GPL-2.0** | Strong copyleft | The previous version of the GPL, from 1991, still used by well-known projects such as Linux. The idea is the same as GPL-3.0, but it doesn't address patents and is incompatible with Apache-2.0 and with GPL-3.0 itself. For a new project, prefer GPL-3.0, unless you depend on code only available under GPL-2.0. |
| **AGPL-3.0** | Strong copyleft | GPL-3.0 with an extra rule for the web: whoever offers a modified version over a network (a web app, for example) must give its users access to that version's code. It's the licence that keeps improvements to a web app open. Some companies avoid it for exactly that reason. |
| **EUPL-1.2** | Copyleft | The European Union's open source licence, equally valid in every official EU language, Portuguese included. Like the AGPL, it also covers services made available online. A compatibility clause lets the code be combined with projects under the GPL, AGPL, LGPL, MPL and others. |
| **LGPL-3.0** | Weak copyleft | Designed for libraries: programs that merely use the library can have any licence, even a closed one. But whoever changes the library itself and distributes it must share those changes under the LGPL. It makes sense if you built a component you want widely used without losing the improvements made to it. |
| **MPL-2.0** | Weak copyleft | The copyleft applies file by file: whoever changes an MPL file must share that file, but may combine it with files under any licence, including closed ones. It's a middle ground between MIT and the GPL. It's compatible with the GPL. |
| **Unlicense** | Public domain | Dedicates the work to the public domain: anyone can do anything, without crediting you. It includes a fallback permissive licence for countries where waiving rights isn't possible. It was written with US law in mind, and some lawyers consider it less robust in Europe. |
| **CC0-1.0** | Public domain | Waives all rights as far as the law allows and, where that isn't possible, works as a very permissive licence. It's the usual choice for data and tables you want to circulate without restrictions. It isn't OSI-approved because it expressly excludes patents, so the listing won't get the Open source badge. |
| **CC BY 4.0** | Creative Commons | Anyone may use, share and adapt the content, even commercially, as long as they credit you, state the licence and indicate changes. It's the simplest way to share a protocol, a flowchart, a presentation or a simple spreadsheet. It isn't designed for code. |
| **CC BY-SA 4.0** | Creative Commons | The same as CC BY, but adapted versions must be shared under the same licence: it's the "copyleft" of content. It's Wikipedia's licence. A good choice for materials you want improved together, such as guides for residents. |
| **CC BY-NC 4.0** | Creative Commons | Anyone may use and adapt it, crediting you, but not for commercial purposes. The problem is defining what's commercial: a private clinic or a paid course, for example, may fall into a grey area. It isn't an open licence and the listing won't get the Open source badge. |
| **CC BY-NC-SA 4.0** | Creative Commons | Combines the two previous restrictions: no commercial use, and adapted versions must keep the same licence. It's the most restrictive Creative Commons licence on this list. It has the same ambiguity problems as CC BY-NC. |
| **Proprietary / closed source** | Proprietary | You keep all rights and set the rules yourself, for example in terms of use. Closed doesn't mean paid: a free tool can be proprietary. Colleagues can use it, but can't adapt it or check how it works. |
| **Unknown** | — | Use it only if you really don't know the licence. In practice, without a licence full copyright applies, so colleagues can't adapt or redistribute the tool. If the tool is yours, pick a licence: it takes two minutes. |

## Simple cases

### "I made a calculator and want anyone to use and adapt it, no strings attached"

**MIT.** It's short, well known and easy to comply with: anyone may use, change and share it, as long as they keep your name and the licence text. It's the most common choice for small tools and a good default.

### "I want improvements made by others to stay open too"

**GPL-3.0.** Anyone who distributes a modified version of your tool must make it available under the same licence, with the source code. So if a colleague improves your tool and shares it, the improvement is available to everyone again.

### "It's a web app running on a server"

**AGPL-3.0.** The GPL only requires sharing when the program is *distributed*; running it on a server and offering it on the web is not distribution. The AGPL closes that gap: anyone offering a modified version over the internet must share the code. If you don't mind someone making a closed version, MIT is still a valid choice.

### "I work in a public health service and prefer a European licence"

**EUPL-1.2.** It's the European Union's open source licence, with equally valid versions in every official EU language, Portuguese included. It's copyleft, also covers services made available online, and is compatible with other well-known licences such as the GPL and the MPL. A good choice for tools linked to public institutions.

### "A company may end up using the code and I'm concerned about patents"

**Apache-2.0.** It's permissive like MIT, but includes an explicit patent grant and clearer rules on contributions. It's longer, but gives more legal certainty in larger projects.

### "It isn't code: it's a spreadsheet, a protocol, a flowchart or teaching material for residents"

**CC BY 4.0** (anyone may use and adapt it, as long as they credit you) or **CC BY-SA 4.0** (the same, but adapted versions must keep the licence). Creative Commons licences were made for content, and Creative Commons itself [advises against using them for software](https://creativecommons.org/faq/). If the spreadsheet has substantial macros or scripts, treat that part as code (MIT or GPL, for example).

### "I don't want anyone making money from this"

**CC BY-NC 4.0** or **CC BY-NC-SA 4.0**, with two caveats. First, the "non-commercial" clause is more ambiguous than it looks: is a private clinic using the tool in consultations making commercial use? Second, NC licences are not open source, so the listing won't get the Open source badge. Before choosing, ask yourself whether the risk of someone profiting justifies keeping away people who could help. Often a copyleft licence (GPL or AGPL) protects what worries you without these drawbacks.

### "I don't care: do whatever you want"

**CC0-1.0** or **Unlicense.** You give up your rights as far as the law allows. CC0 is better prepared for countries, such as Portugal, where it isn't possible to waive all copyright: there it works as a very permissive licence. In practice, MIT gives almost the same freedom and keeps your name attached to the work.

### "I don't want to share the code"

**Proprietary / closed source.** It's a legitimate choice, and the tool can still be listed on gitmgf. Colleagues can use it, but they can't adapt it or check how it does its calculations, and the listing won't get the Open source badge. In healthcare, being able to see how a calculation is done is a real advantage; it's worth weighing that.

## Quick summary

| If you want… | Choose |
|---|---|
| The simplest, freest option, keeping your name on it | MIT |
| Modified versions to stay open | GPL-3.0 |
| The same, for a web app | AGPL-3.0 |
| A European licence, official in Portuguese | EUPL-1.2 |
| Explicit patent protection | Apache-2.0 |
| To share a document, protocol or simple spreadsheet | CC BY 4.0 |
| To give up all rights | CC0-1.0 |
| To keep the code closed | Proprietary |

If you're still undecided, pick **MIT** for code and **CC BY 4.0** for content. To compare other options, [choosealicense.com](https://choosealicense.com) (by GitHub) and the [Creative Commons chooser](https://creativecommons.org/chooser/) help you decide in a few clicks.

## How to apply the licence

1. **In the repository:** create a file called `LICENSE` in the root folder. On GitHub, under **Add file → Create new file**, type `LICENSE` as the name and a **Choose a license template** button appears, which fills in the text, the year and your name.
2. **In a spreadsheet or document:** add a visible line, for example on an "About" sheet or in the footer: *"© 2026 First Last. Licensed under CC BY 4.0: https://creativecommons.org/licenses/by/4.0/"*.
3. **On gitmgf:** choose the same licence on the listing form. Moderation checks that the stated licence matches the repository, and the listing also shows the licence GitHub detects.

## Before choosing, check three things

- **Who owns it?** If you created the tool as part of your job or on commission, Portuguese law may give the rights to your employer or to whoever commissioned it, unless agreed otherwise. If the tool was born inside a health unit, a funded project or a company, first check who can decide the licence.
- **What did you use from others?** If the tool includes code, libraries, scales or tables from third parties, your licence must be compatible with theirs. For example, if you use a GPL library and distribute the whole, your tool must also be GPL. Published clinical scales may have their own rights; check before reproducing them.
- **A licence doesn't replace clinical care.** Almost all open source licences say the software is provided "as is", without warranty. That limits your liability as an author, but doesn't spare you from validating the calculations, citing sources and stating the limits of use. Nor does it change the medical device rules: whether a tool may be a medical device depends on its intended purpose, not its licence.

## Can I change my mind later?

Yes, within limits. If you're the sole author, you can release later versions under a different licence. Versions you've already shared keep their original licence: whoever received them keeps those rights. If other people have contributed code, you need their agreement to relicense the parts they wrote.

So it's worth thinking about it for a few minutes now. But don't let this choice delay publishing: a tool online under MIT is more useful than a perfect tool waiting for the ideal licence. When it's ready, [share it on gitmgf](/me/tools/new).
