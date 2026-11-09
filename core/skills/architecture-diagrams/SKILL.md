---
name: architecture-diagrams
description: Use when producing architecture, deployment, network, data-flow or security diagrams that people will edit later, especially Azure solutions. Sets the kit's rules for using the pinned third-party drawio-skill (Diagram IR → editable draw.io) with official Azure icons, offline only.
---

# Architecture diagrams (via drawio-skill)

## Overview
Diagrams are made with **drawio-skill** (github.com/Agents365-ai/drawio-skill,
MIT), pinned to a reviewed commit. See `THIRD_PARTY.md` at the kit root for
the pin, the review scope and the allowed features. This skill adds the
kit's rules on top. It doesn't replace drawio-skill's own SKILL.md.

The route is the **Diagram IR**: a JSON model of nodes and edges with
semantic properties and provenance. It's built into an editable `.drawio`
file with `diagramctl.py build model.ir.json --from ir`. The same IR can be
projected into views (executive, system, deployment, dataflow, security),
and `whatif` checks failure impact. Both suit architecture reviews.

## Icon rules (Microsoft Azure icons)
Microsoft permits the Azure icons in architecture diagrams, training and
documentation. Don't crop, flip, rotate, distort or recolour them, and don't
use a Microsoft icon for a non-Microsoft product.
Source: https://learn.microsoft.com/en-us/azure/architecture/icons/

- **Use only `img/lib/azure2/...` styles.** These are draw.io's bundled copy of
  the Microsoft Azure icon set. **Don't** use the legacy `mxgraph.azure.*` shapes
  (an older, unofficial look). The index has both.
- **Never guess a style.** Take it from the shape index:
  `python3 scripts/shapesearch.py "azure key vault"` (interactive), or, in an
  audit, from `.audit/scans/drawio-azure-shapes.json`.
- Several entries share a name (e.g. App Services under `app_services/`,
  `compute/`, `containers/`). Pick one category and use it consistently.
- An icon not in the index (very new services): ask the person running the
  build to embed it from the official SVG pack, or use a plain labelled box.
  Never substitute a look-alike.
- Label every icon with the product name near it, as Microsoft asks.

## Allowed and not allowed (council use)
| Allowed (offline) | Not allowed without a separate review and approval |
|---|---|
| `diagramctl.py build --from ir`, `views`, `inspect`, `query`, `whatif`, `test`, `review`, `sync` | `aiicons.py` / `dbxicons.py` (fetch icons from CDNs); IR or diagrams that reference remote icon URLs |
| `validate.py`, `autolayout.py` (local Graphviz), `shapesearch.py` | Live infrastructure capture (`tfstate.py`, `dockerimports.py`, `k8simports.py`) |
| Native export with the local draw.io CLI | `diagramctl_mcp.py` (MCP server), `prdiff.py` PR bot, any publishing to remote services |
| | `--refresh-manifest` and any other maintainer operation |

## Drawing for people (layout and labels)
A diagram is read in about ten seconds. Draw it the way an architect would at a
whiteboard, not as a dump of every fact found:

- **Context first, detail second.** `as-is.ir.json` and `target.ir.json` are
  context diagrams: **at most 15 nodes and 20 edges**. Detail (local files,
  in-process state, each background job, each AI call) goes in extra
  diagrams that each answer one question, e.g. `as-is-integrations.ir.json`,
  `as-is-data.ir.json`.
- **Fold siblings into one node.** Three Azure AI services called from one place
  become "Azure AI services / OpenAI, Content Safety, Vision" (a plain node, since
  no single Microsoft icon fits). Same for "Microsoft 365 / SharePoint, mail,
  Teams" and "Council databases".
- **Short labels.** Node `label`: product name, a line break (`\n`), then the role
  in at most five words ("Report It\npublic app + jobs"). Edge `label`: at most
  three words, the protocol or purpose ("Blob SDK", "OIDC", "enqueue"). The
  detail (settings, caveats, "not determinable") goes in `properties.description`
  and the report, never the label.
- **One edge per pair and direction.** Merge parallel calls into one edge.
- **Group every node** with `group`, a path of trust zones:
  `Internet`, `Azure/App Service`, `Azure/Storage`, `Microsoft 365 and Entra`,
  `Council network`, `Third-party SaaS`. If `group` is missing, the build uses
  `properties.trust_boundary` instead.
- `kind: async` on queue and fire-and-forget edges (they're drawn dashed).

## House style (applied by `kit diagrams`)
The kit lays the diagram out left to right (internet → Azure → what it calls)
and restyles it after drawio-skill builds it (`src/audit_kit/diagram_style.py`):
rounded, lightly tinted trust zones; nodes as rounded cards with the Azure icon
at a fixed 40 px on the left (never distorted); curved edges; data stores
as cylinders; a hand-drawn stroke. `kit diagrams <ws> --style clean` gives
the same layout without the hand-drawn stroke, for formal documents. Don't
put colours, fonts or sizes in the IR: the house style replaces them.
Exception: an Azure icon's `style` (the `image=` path) is required.

## Process
1. **Purpose first.** One question per diagram. As-is and target are separate.
2. **Write the IR** (`drawio-skill/references/diagram-ir.md`). Per node: a
   stable `id`, `label` (product name + role), `kind`, a `style` copied
   exactly from the shape index for Azure icons, `properties` such as
   `trust_boundary`, `environment`, `region`, `data_classification` and
   `importance` (`low`, `medium`, `high` or `critical`; these drive the security, deployment and executive views; without
   them a view falls back to the whole model and says so), and `provenance` (`path` and
   `line` of the evidence). Per edge: `source`, `target`, `label` (protocol or
   purpose), `kind` (`sync` / `async`), `properties.protocol`.
3. **Build:** `kit diagrams <workspace>` (groups, builds left to right, makes the
   views and applies the house style). By hand: `python3 scripts/diagramctl.py build
   model.ir.json --from ir -o model.drawio --direction LR`, then `views …`.
4. **Check:** `python3 scripts/validate.py model.drawio --score`.
5. **Tidy in draw.io.** Keep the file uncompressed (File → Properties).
   Later source changes go through `sync`, which keeps manual layout.
6. **Export** with the local draw.io CLI (see drawio-skill's export rules): SVG
   for Markdown and Marp slides, PNG at 2× for Word and PowerPoint (skill
   `audit-publishing`). Commit `.ir.json`, `.drawio` and exports together.

## Beyond pictures (all offline, on the same IR)
| Need | drawio-skill feature | Reference |
|---|---|---|
| Deterministic architecture checks ("internet never reaches the database directly", "every service has an owner") | Architecture contracts: `diagramctl.py test model.drawio --rules policy.yml`. Pure Python, so it also runs in Azure Pipelines | `references/semantic-workflows.md`, `references/ci-gate.md` (GitHub Actions examples; port the commands) |
| Failure mode analysis | `diagramctl.py whatif model.ir.json --fail <node>` | `references/semantic-workflows.md` |
| Audience-specific pages | `views --views executive,system,deployment,dataflow,security` | `references/diagram-ir.md` |
| Database diagram from SQL DDL | `diagramctl.py build <ddl.sql> --from sql` | `references/cookbook.md` |
| Prompt patterns and anti-patterns | Cookbook | `references/cookbook.md` |

Treat `review` output and inferred relationships as prompts for a human, not
verified facts. drawio-skill says the same.

## In an audit
Agents can't run scripts. The architect writes `.audit/diagrams/<name>.ir.json`
with styles taken from `.audit/scans/drawio-azure-shapes.json` and provenance
pointing at the evidence (`file:line`). The tech lead runs the build, views and
validate commands (see `docs/how-to-run-an-audit.md`).

## Red flags
- A context diagram over 15 nodes or 20 edges, or a label longer than one line plus a role
- Nodes with neither `group` nor `properties.trust_boundary` (they float outside every zone)
- A style string that isn't in the shape index, or uses `mxgraph.azure.`
- A Microsoft icon on a non-Microsoft system (use `kind` shapes for a CRM, SaaS or people)
- Relationships in the diagram with no provenance (an inferred link presented as fact)
- Remote icon URLs in the output (breaks offline use; leaks viewing to a CDN)

## Verification
- [ ] Built from IR with the pinned drawio-skill commit; `validate.py --score` run
- [ ] Every Azure icon is an `img/lib/azure2/` style from the index, labelled with the product name
- [ ] Boundaries and trust zones shown; provenance on nodes and edges
- [ ] Context diagrams within 15 nodes and 20 edges; detail in separate diagrams
- [ ] `.ir.json`, `.drawio` and exports committed together
