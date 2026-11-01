---
inclusion: always
---

# Product — Green Screen Séance

## One line
Point Green Screen Séance at a legacy IBM 3270 green-screen mainframe app and talk to it in plain English. It reads the screens, fills the fields for you, and learns the app well enough to expose it as typed MCP tools that any AI agent can use — without rewriting the legacy code.

## Category
Kiroween 2026 — **Frankenstein** (stitch technologies that don't usually work together: a 1970s COBOL/3270 mainframe + modern LLM agents via MCP).

## The problem it solves
Banks, insurers and councils still run core business logic on COBOL/mainframe systems that most staff can't operate. Modernising means a risky, expensive rewrite. Green Screen Séance lets people use those systems through a conversational AI layer that actually drives the real screens — no rewrite, the legacy code stays untouched.

## How it works (end to end)
1. A 3270 bridge opens a real terminal session to the legacy app (TK4- / MVS 3.8j on Hercules, in Docker for the demo).
2. An "explorer" safely navigates the app read-only and records a **spirit map** — a graph of screens, fields and the keys that move between them.
3. An LLM labels screens/fields with business meaning, and a generator turns the spirit map into **typed, business-level MCP tools** (e.g. `lookup_policy(policy_number)`).
4. A chat agent calls those tools to fulfil user requests, streaming each step to the UI. A "planchette" pointer glides over the green screen so users can see what the AI is doing.
5. Anything that could change data goes through an explicit confirmation step and is written to an append-only audit log.

## Demo scope
One demo business app, ~5 screens (e.g. insurance policy enquiry/update), done really well. Prioritise a complete, polished end-to-end experience over breadth. The demo path must work three times in a row.

## What this is NOT
- Not a mainframe rewrite or code translator.
- Not real z/OS — TK4- is a free MVS 3.8j distribution for development/demo.
- Not a generic screen scraper — the value is the auto-generated business-level tools and the conversational layer, not raw terminal automation.
