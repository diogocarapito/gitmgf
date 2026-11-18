---
title: "How I built gitmgf in 8 hours with Claude Pro and Claude Code"
date: 2026-11-18
author: Diogo Carapito
summary: "From idea to a live site in one day: a PRD and tech spec in Claude, design and logo with artifacts, the code with Claude Code, and deployment on a European VPS with its own domain."
---

gitmgf went from an idea to a public website in about 8 hours of work. I didn't write the code by hand: I wrote down what I wanted, reviewed what Claude proposed, and made the decisions. This article walks through the process step by step, for anyone who wants to do the same with a tool for their own clinical practice.

**What you need:** a Claude Pro subscription (it includes Claude Code), a GitHub account, a domain and a virtual private server (VPS). Rough total: about €30 in the first month and under €30/month after that (see the summary at the end).

## 1. Write the PRD and the tech spec in Claude

Everything starts in a new chat at [claude.ai](https://claude.ai) (the **+ New chat** button). The goal of this phase is two documents:

- **`PRD.md`** (Product Requirements Document): the what and why. Who it's for, which problems it solves, what the MVP includes, what waits for later, and acceptance criteria for each feature.
- **`TECH_SPEC.md`**: the how. Technologies, data model, routes, security, privacy, tests, and a plan in milestones, each with a "definition of done".

What worked best was asking Claude to interview me before writing anything:

> I want to build a portal where family doctors share digital tools they built for clinical work. Ask me questions, one at a time, until you have enough information. Then write a `PRD.md` with goals, users, MVP features with acceptance criteria, out of scope, and open questions.

Then, in the same chat:

> Based on the PRD, write a `TECH_SPEC.md` for a simple MVP one person can maintain: Python, FastAPI, SQLite, no frontend framework, hosted on an EU VPS with Docker. Include the data model, security, GDPR, tests and milestones with a definition of done.

Read everything carefully and fix whatever doesn't match what you want: these two files are the "contract" Claude Code will follow. I also had Claude write a **`CLAUDE.md`** (project conventions: commands, code rules, European Portuguese vocabulary) and drafts of the legal texts (terms, privacy). **Generated legal texts are only a starting point and should be reviewed by someone qualified.**

## 2. Design and logo with artifacts

Claude's artifacts show the result next to the chat, which is great for design. I asked for:

> Create a single-page HTML mockup of the gitmgf visual system: palette, typography, buttons, tool cards, home page, search and a tool page, in light and dark mode, mobile first.

And, separately, the logo:

> Design an SVG logo for "gitmgf": simple, legible at small sizes, with a version for dark backgrounds.

I iterated a few times ("fewer shadows", "a calmer primary colour") and downloaded the HTML and the SVGs.

## 3. Put everything in a folder and open Claude Code

I put all the documents in one folder, roughly like this:

```
gitmgf/
├── PRD.md
├── TECH_SPEC.md
├── CLAUDE.md
├── design/      (mockup.html, logo.svg, logo-dark.svg)
└── legal/       (draft terms and privacy policy)
```

I installed [Claude Code](https://claude.com/claude-code) (see the official docs for other systems) and started it inside the folder:

```bash
curl -fsSL https://claude.ai/install.sh | bash
cd gitmgf
claude
```

The first time, it asks you to sign in with your Claude account. My first request was literally:

> Let's create an MVP with the documents I've compiled, to be deployed to a VPS.

From there, Claude Code read the documents and built the app milestone by milestone: project foundation, authentication, tool submission, moderation, search, scoring, compliance and, finally, hardening and deploy scripts. At each step it writes tests and runs them before moving on.

What helped:

- **Work in milestones.** Don't move on until the previous one meets its definition of done.
- **Decide, don't code.** When there was a product choice (for example, switching sign-in to email + password), I decided and Claude recorded the decision in `docs/DECISIONS.md`.
- **Try it in the browser.** The tests passed, but using the site for real revealed a bug in the forms. Automated tests don't replace trying things out.
- **Breaks.** The Pro plan has usage limits that reset after a few hours; in a long session you'll sometimes have to wait.

## 4. Create a public GitHub repository

With the app working locally, I created a GitHub repository and pushed the code. With the [GitHub CLI](https://cli.github.com):

```bash
git init && git add . && git commit -m "feat: MVP"
gh repo create gitmgf --public --source=. --push
```

Or create the repository on github.com and then:

```bash
git remote add origin https://github.com/<username>/gitmgf.git
git push -u origin main
```

**Before making it public:** check that `.env` (passwords, keys) is in `.gitignore` and that no secret ever made it into the history. The gitmgf code is at [github.com/diogocarapito/gitmgf](https://github.com/diogocarapito/gitmgf).

## 5. Buy a domain

Two registrars with fair prices and no renewal tricks:

| Registrar | `.com` per year (approx.) | Notes |
|---|---|---|
| [Cloudflare Registrar](https://www.cloudflare.com/products/registrar/) | ≈ US$10–11 | At cost. DNS stays on Cloudflare, which also gives you a free proxy, HTTPS and email forwarding |
| [Porkbun](https://porkbun.com) | ≈ US$11–12 | Simple interface, private WHOIS included |

Once you have the server (next step), add an `A` record for the domain and another for `www`, both pointing at the VPS IP. On Cloudflare, with the proxy on, set SSL/TLS to **Full (strict)**.

## 6. Rent a VPS

A VPS is a virtual server rented by the month. A small one is enough for an MVP like this, but I recommend **at least 2 GB of RAM** (building Docker images with 1 GB is tight) and **Ubuntu 24.04 LTS**. If your app handles personal data of European users, an EU provider and data centre make GDPR simpler.

**In Europe:**

| Provider | Example plan | Approx. price | Notes |
|---|---|---|---|
| [Hetzner](https://www.hetzner.com/cloud) (Germany, Finland) | CX23: 2 vCPU, 4 GB RAM, 40 GB | ≈ €5.50–6/month | Excellent console, hourly billing, backups and object storage in the same place |
| [netcup](https://www.netcup.com/en/server/vps) (Germany, Austria) | VPS 1000 G11 | ≈ €6–8/month | Lots of RAM and disk for the price; some prices require a 12-month minimum term |

**In the US:**

| Provider | Example plan | Approx. price |
|---|---|---|
| [DigitalOcean](https://www.digitalocean.com/pricing/droplets) | Basic, 1 GB / 2 GB | ≈ US$6 / 12 per month |
| [Vultr](https://www.vultr.com/pricing/) | Cloud Compute, 1 GB / 2 GB | ≈ US$5 / 10 per month |
| [Akamai (Linode)](https://www.linode.com/pricing/) | Nanode 1 GB / Shared 2 GB | ≈ US$5 / 12 per month |

Hetzner also has US data centres (Ashburn and Hillsboro). *Approximate prices as of November 2026, before VAT/sales tax; they change often, so check each provider's pricing page.*

When you create the server, **add your public SSH key right away** (`cat ~/.ssh/id_ed25519.pub`; if you don't have one, create it with `ssh-keygen -t ed25519`). Signing in with a key instead of a password is safer and keeps you from getting locked out.

## 7. Prepare the server and deploy the MVP

First, as `root`, prepare the server: updates, Docker, a firewall and an unprivileged user for deploys.

```bash
ssh root@<server-ip>
apt update && apt -y upgrade
curl -fsSL https://get.docker.com | sh
adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
mkdir -p /home/deploy/.ssh && cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
ufw allow OpenSSH && ufw allow 80,443/tcp && ufw --force enable
```

**Before closing that session**, open another terminal and check that `ssh deploy@<server-ip>` works. SSH configuration changes are the most common way to lose access.

Then, as `deploy`, fetch the code, configure it and start it:

```bash
ssh deploy@<server-ip>
git clone https://github.com/<username>/gitmgf.git && cd gitmgf
cp .env.example .env
nano .env          # domain, secret key, admin email…
docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
```

In gitmgf, Caddy (the web server) gets the HTTPS certificate automatically on first start, as long as DNS already points at the server. To ship a new version:

```bash
git pull && docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
```

In the gitmgf repository these steps are ready-made scripts (`deploy/setup-vps.sh` and `deploy/deploy.sh`), described in `docs/RUNBOOK.md`. **Always read a script before running it as root.**

## 8. Optional: email

To send confirmation codes and notifications I used [Brevo](https://www.brevo.com) (SMTP; the free plan is enough to start), and to receive mail at `contacto@` without running a mailbox, Cloudflare's free email routing. Two errors I hit: `535 Authentication failed` (it needs the *SMTP key*, not the API key) and `525 Unauthorized IP address` (Brevo blocks new IPs until you authorise them under *Security → Authorised IPs*).

## What I learned

- **The documents are the most important work.** A clear PRD saves hours of fixes. The more concrete the acceptance criteria, the better the result.
- **Claude writes; you're responsible.** Review what gets built, especially security, privacy and legal texts. For a clinical tool, this isn't optional.
- **Production problems are almost always configuration.** My Cloudflare 521 and 525 errors were missing `.env` values and a certificate still being issued, not bugs in the code.
- **Start small.** A €5 server handles far more than you'd think with SQLite and a simple app.

## Cost summary

| | Approx. cost |
|---|---|
| Claude Pro (includes Claude Code) | ≈ US$20/month (≈ US$17/month billed annually) |
| EU VPS | ≈ €5–8/month |
| `.com` domain | ≈ US$10–12/year |
| Email (Brevo free plan) and Cloudflare | €0 |

If you build a useful tool for clinical practice this way, [share it on gitmgf](/en/me/tools/new).
