# Anton AI Audit & Documentation Workflow

This document contains a series of prompts intended for a frontier LLM to perform a comprehensive audit of the Anton codebase.

The goal is **not** to immediately modify the project.

The goal is to build the documentation and operating system that every future AI coding session will rely on.

---

# General Instructions

For every prompt below:

* Read the entire repository before responding.
* Prefer understanding over making assumptions.
* Do not make code changes unless explicitly requested.
* If something is unclear, explain the uncertainty.
* Think like a senior software architect performing a technical due diligence review.
* Assume Anton is a long-term personal platform rather than a single-purpose application.

---

# Prompt 1 — Architecture Audit

## Goal

Understand the complete system architecture.

Produce:

```
docs/
    architecture.md
```

Include:

* High-level architecture
* Technology stack
* Folder structure
* Request lifecycle
* Database architecture
* Services
* API layer
* AI layer
* Scraper architecture
* Authentication
* Data flow
* External integrations
* Major dependencies
* Domain model
* Current strengths
* Architectural weaknesses
* Recommended long-term improvements

Do not suggest implementation changes here.

This document should become the primary technical reference for Anton.

---

# Prompt 2 — Current Project State

Produce:

```
docs/project_state.md
```

Include:

* Current development status
* Features completed
* Features partially complete
* Features planned
* Known bugs
* Technical debt
* Current blockers
* Recent architectural decisions
* Current branch assumptions
* Areas requiring immediate attention

The goal is to allow a new AI model to understand the project within minutes.

---

# Prompt 3 — Product Roadmap

Produce:

```
docs/roadmap.md
```

Assume Anton is evolving into a long-term personal AI platform.

Organize into:

## Phase 1

Immediate priorities

## Phase 2

Core platform

## Phase 3

AI capabilities

## Phase 4

Automation

## Phase 5

Long-term vision

For each item include:

* Description
* Why it matters
* Dependencies
* Estimated complexity
* Suggested implementation order

---

# Prompt 4 — Claude Development Guide

Produce a completely fresh

```
CLAUDE.md
```

The document should contain:

* Coding philosophy
* Project overview
* Folder conventions
* Architecture principles
* Coding standards
* Preferred patterns
* Error handling
* Logging expectations
* Database conventions
* Testing expectations
* Refactoring philosophy
* Performance expectations
* Documentation standards

The objective is for Claude Code to consistently generate code matching the project's style.

---

# Prompt 5 — Skills Library

Create a suggested skills library.

Output:

```
.claude/
    skills/
```

Suggest one markdown file for each repeatable development workflow.

Examples:

* add-api-endpoint.md
* add-retailer.md
* add-database-model.md
* write-tests.md
* refactor-service.md
* scraper-pattern.md
* ai-agent.md
* background-job.md
* debugging.md
* deployment.md

For each skill include:

* Purpose
* When it should be used
* Required context
* Step-by-step workflow
* Common mistakes
* Checklist

Do not implement the files.

Design the structure only.

---

# Prompt 6 — Code Review

Perform a senior-level code review.

Produce:

```
refactoring/refactor.md
```

Split findings into:

## Critical

Must fix immediately.

## High Impact

Large improvements.

## Medium Impact

Worth improving.

## Low Priority

Nice improvements.

Each finding should contain:

* Description
* Why it matters
* Suggested solution
* Estimated effort
* Estimated risk

Focus on maintainability rather than micro-optimizations.

---

# Prompt 7 — Dead Code Analysis

Produce:

```
refactoring/dead_code.md
```

Identify:

* Definitely unused files
* Probably unused files
* Legacy experiments
* Duplicate implementations
* Unused API routes
* Unused models
* Unused utilities
* Unused tests
* Obsolete scripts
* Unreachable code

For every finding include:

* Confidence level
* Why it appears unused
* Whether it is safe to delete
* Dependencies that should be checked first

Do not delete anything.

---

# Prompt 8 — Technical Debt Report

Produce:

```
refactoring/tech_debt.md
```

Include:

* Architectural debt
* Naming inconsistencies
* Large files
* God objects
* Circular dependencies
* Poor abstractions
* Tight coupling
* Missing tests
* Missing documentation
* Missing typing
* Fragile areas

Rank everything by impact.

---

# Prompt 9 — Dependency Graph

Produce:

```
docs/dependency_graph.md
```

Map:

Application Entry Points

↓

API Layer

↓

Services

↓

Repositories

↓

Database

↓

External APIs

Also identify:

* Circular imports
* Hidden dependencies
* Tight coupling
* Layer violations

Provide suggestions for simplification.

---

# Prompt 10 — AI Context Document

Produce:

```
docs/ai_context.md
```

This document should become the first thing any future AI assistant reads.

Include:

* What Anton is
* Long-term vision
* Project philosophy
* Folder structure
* Architecture summary
* Important design decisions
* Coding conventions
* Things that should never be changed casually
* Current priorities
* Current roadmap
* Known technical debt
* Recommended reading order for project documentation

Keep this concise while maximizing information density.

---

# Prompt 11 — Design Decisions

Produce:

```
docs/design_decisions.md
```

Identify important architectural decisions already present in the project.

For each decision explain:

* What was chosen
* Why it was probably chosen
* Advantages
* Trade-offs
* Whether the decision should remain

This should become the historical record for future development.

---

# Prompt 12 — Domain Model

Produce:

```
docs/domain_model.md
```

Document:

* Core entities
* Relationships
* Business rules
* Ownership boundaries
* Data lifecycle
* Naming conventions

Explain the business domain rather than implementation details.

---

# Final Review Prompt

After completing all previous prompts:

Review every generated document together.

Identify:

* Missing documentation
* Contradictions
* Overlap
* Inconsistencies
* Gaps in architecture
* Missing skills
* Missing design decisions

Produce a final report recommending improvements to the documentation itself.

---

# Phase 2 (Implementation)

Once all documentation has been reviewed and accepted:

* Create implementation plans.
* Break work into small milestones.
* Use lower-cost coding models or coding agents to execute each milestone.
* Continuously update:

  * project_state.md
  * roadmap.md
  * design_decisions.md

Treat these documents as living project artifacts rather than one-time outputs.

The objective is to ensure every future AI session begins with accurate, concise, high-quality context instead of relying on long conversation histories.
