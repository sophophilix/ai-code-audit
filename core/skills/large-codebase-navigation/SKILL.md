---
name: large-codebase-navigation
description: Use when files are too large to read in one pass (thousands of lines), when one-line-heavy code makes reading slow, or when tracing a behaviour across many files.
---

# Large codebase navigation

## Overview
Reading whole large files wastes context and still misses things. Search,
then read narrow ranges, and reuse what discovery already mapped.

## Process
1. **Reuse first.** Read the "Behaviour map", "Routes" and "Integrations"
   sections of `.audit/01-discovery.md` before opening code.
2. **Measure.** Use `.audit/scans/cloc.json` or `wc -l`. Note files over
   1,000 lines and files with very long lines (`awk 'length > 200'`). Long
   lines hide logic from line-based reading.
3. **Search, don't scroll.** Use the search patterns in the active stack
   profile (routes, outbound calls, config reads, file writes, logging,
   dangerous sinks). Use `grep -n` so every hit has a line number.
4. **Read targeted ranges** around each hit (`sed -n 'START,ENDp'`), wide
   enough to see guards and error handling. Include the caller if behaviour
   depends on it.
5. **Follow the data.** For a flow, go from entry (route) to validation to
   business logic to outbound call to response, and record each hop as `file:line`.
6. **Delegate broad sweeps** to your harness's read-only search helper if it
   has one. Ask for a digest with `file:line` references only, not conclusions.

## Red flags
- Claiming a file "does nothing else" without having searched it
- Summaries with no line references
- Reading the same large file from top to bottom twice
- Treating a grep hit as proof without reading the surrounding lines
