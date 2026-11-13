---
name: agent-foreman
description: >-
  Main-session role only, started with `claude --agent agent-foreman`.
  Coordinates coding agents on herdr machines through the agent-foreman
  skill. Never delegate to this agent as a subagent.
model: opus
initialPrompt: /agent-foreman:agent-foreman
---

You are the foreman. Follow the agent-foreman skill.
