# Smart Exploration Prompt Library

Subagent dispatch prompts organized by task category. Each prompt is a complete instruction ready to pass directly to an Agent tool call. Fill in placeholders (`[FEATURE]`, `[AREA]`, `[TARGET]`) from the user's request before dispatching.

All prompts use `think harder about...` as the default thinking budget (deep analysis, ~10K tokens). This matches Phase 2's default in `claude-flow`.

---

## endpoint

Use when adding or modifying API routes, controllers, handlers, or REST/GraphQL endpoints.

**Explorer A — Route/service/model chain:**

> variant_id: endpoint:route-chain

> think harder about... Trace the route → service → model chain for the nearest similar endpoint to [FEATURE]. Find the route definition, the controller or handler that processes it, the service layer it calls, and the model(s) it reads or writes. Note how the response is shaped and what status codes are used. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

**Explorer B — Middleware, auth, and error handling:**

> variant_id: endpoint:middleware-auth

> think harder about... Map the middleware, auth, and error handling patterns for routes in this area. Find how authentication and authorization are enforced, what middleware runs before the handler, how validation errors and server errors are returned, and whether there are shared error response formats. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

---

## ui

Use when making frontend or template changes — components, pages, CSS, or state management.

**Explorer A — Component tree, CSS, and state:**

> variant_id: ui:component-tree

> think harder about... Map the component tree, CSS architecture, and state management for [AREA]. Find the top-level page or view component, its children, how styles are organized (modules, utility classes, theme tokens), and where state lives (local, context, store). Note any shared UI primitives being reused. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

**Explorer B — Data flow from API to rendered template:**

> variant_id: ui:data-flow

> think harder about... Trace the data flow from API call to rendered template for the nearest similar page to [FEATURE]. Find where the API is called, how loading and error states are handled, how data is transformed before rendering, and how the final values appear in the template or JSX. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

---

## data

Use when changing models, database migrations, queries, schema, or ORM relationships.

**Explorer A — Model relationships and cascade behaviors:**

> variant_id: data:model-relationships

> think harder about... Trace the model relationships, foreign keys, and cascade behaviors for [AREA]. Find the relevant model definitions, their associations (has-many, belongs-to, many-to-many), any soft-delete or audit fields, and what cascades on delete or update. Note any constraints enforced at the DB level vs. application level. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

**Explorer B — Migration history and query patterns:**

> variant_id: data:migration-queries

> think harder about... Map the migration history and query patterns used for this data. Find recent migrations that touched the same tables, how schema changes were structured, and how the application queries this data (raw SQL, ORM methods, scopes, indexes). Note any performance-sensitive query patterns. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

---

## integration

Use when connecting to or modifying external APIs, webhooks, or third-party services.

**Explorer A — External API call sites and error handling:**

> variant_id: integration:api-call-sites

> think harder about... Find all external API call sites, auth patterns, retry logic, and error handling for this integration. Locate where the HTTP client is initialized, how credentials are managed, what headers or tokens are required, how retries and timeouts are configured, and how errors (rate limits, failures, bad responses) are caught and surfaced. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

**Explorer B — Data transformation pipeline:**

> variant_id: integration:data-transform

> think harder about... Map the data transformation pipeline from API response to internal model for [FEATURE]. Trace how raw API responses are parsed, validated, normalized, and mapped to internal types or database records. Note any field renaming, type coercion, or filtering that happens along the way. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

---

## refactor

Use when restructuring existing code without changing behavior — moving, renaming, or abstracting.

**Explorer A — Callers and dependents:**

> variant_id: refactor:callers-dependents

> think harder about... Map all callers and dependents of [TARGET] across the codebase. Find every file that imports, calls, or otherwise depends on the target code. Note the call signatures being used, any assumptions callers make about return types or side effects, and which callers are in tests vs. production code. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

**Explorer B — Test coverage boundary:**

> variant_id: refactor:test-coverage

> think harder about... Identify the test coverage boundary — what tests exercise the code being refactored in [TARGET]. Find the test files that cover this code, what behaviors they assert, which edge cases are tested, and which are not. Note whether tests are unit, integration, or end-to-end, and whether the refactor will require updating test structure. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

---

## bugfix

Use when debugging a defect — tracing an error, unexpected behavior, or regression.

**Explorer A — Execution path to the bug:**

> variant_id: bugfix:execution-path

> think harder about... Trace the execution path that leads to the bug — inputs, transformations, outputs. Starting from the entry point (route, event, job, etc.), follow the code path step by step until you reach the point of failure. Note every transformation, conditional branch, and external call along the way. Identify where the behavior diverges from what is expected. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

**Explorer B — Error handling, logging, and monitoring:**

> variant_id: bugfix:error-logging

> think harder about... Find all related error handling, logging, and monitoring for this code path. Locate where errors are caught, what gets logged and at what level, whether there are any metrics or alerts tied to this path, and how errors are surfaced to the caller or user. Note any silent failure patterns where errors are swallowed. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

---

## config

Use when making configuration, environment variable, infrastructure, or deployment changes.

**Explorer A — Config value flow:**

> variant_id: config:value-flow

> think about this... Map how config values flow from environment → config files → application code for this area. Find where environment variables are declared (`.env.example`, docs, CI config), how they are loaded into the application (config modules, framework config, direct `process.env`), and where in the application they are consumed. Note any validation, defaults, or required vs. optional distinctions. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

---

## general

Fallback when the task doesn't clearly fit another category.

**Explorer A — Similar feature patterns:**

> variant_id: general:similar-features

> think harder about... Trace how similar features are implemented — find patterns, data flow, and key files for [FEATURE]. Look for the closest existing feature in the codebase that resembles what is being built or changed. Map its entry point, data flow, key files, and any conventions it follows. Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.

**Explorer B — Architecture for the area:**

> variant_id: general:area-architecture

> think harder about... Map architecture for this area — key files, layers, dependencies for [AREA]. Identify the main modules or packages involved, how they are layered (e.g., routes → services → models), what external dependencies they rely on, and any architectural patterns in use (e.g., repository pattern, event-driven, MVC). Return: 5-10 key files (with line ranges), patterns to follow, and constraints discovered.
