# ADR 0003: A solution design stage, built on a decision catalogue and the client's standards

> Status: Approved
> Created: 2026-11-07T09:11:55Z
> Last reviewed: 2026-11-07T11:24:55Z
> Next review: Not scheduled

## Review guide

Decision requested: add a solution design stage after Checkpoint 2. It proposes a
target Azure design with options, reasons and diagrams, built from a pinned
catalogue of decisions and secure service baselines, and fitted to the client
organisation's own platform standards.

Check these points:

- [ ] A new `solution-designer` agent rather than a larger `architect` (D1).
- [ ] Two passes with a human choice in between, and the two new checkpoints (D2).
- [ ] The five-part shape of a catalogue entry, and the first decisions to write (D3, D4).
- [ ] Organisation standards as an input that outranks Microsoft guidance, with deviation requests (D5).
- [ ] Standards as constraints, never as evidence of behaviour (D6).
- [ ] The eval plan, including the sample standard in `templates/examples/` (D10).

Respond with one of:

- `approve`
- `approve with follow-up: <action>`
- `request changes: <specific issue>`

## Summary

The kit audits what a system does. It doesn't yet tell a council how to build the
system properly on Azure. The `architect` agent compares three hosting options and
lists what the platform team must build, but it's an auditor: its output is
findings against the as-is system. Teams also need a target design with
justified choices: compute, ingress and load balancing (internal and external),
data store, identity and least privilege, network topology (hub and spoke, VNet
integration, private endpoints, firewall), edge and CDN, build, packaging and
CI/CD. They need diagrams for each, and they need the design to fit the platform
the organisation already runs.

This record adds a fifth stage. A new `solution-designer` agent works in two
passes. Pass A sets out the options for each decision, using a pinned catalogue
that ties each choice to signals in the code and to Microsoft's published decision
guides. The tech lead chooses at a new Checkpoint 3. Pass B writes the detailed
design for the chosen options, applies a secure baseline per service, and checks
every part against the organisation's standards. Where the design must depart
from a standard, it raises a deviation request instead of overriding it.

## Context

### What the kit does today

- `core/agents/architect.md` section 5 compares "at least three realistic options"
  for hosting and writes an ADR. Section 7 lists platform build requirements.
  Both are inside an audit report, judged against the as-is code.
- `profiles/azure-architecture/SKILL.md` holds a principles scorecard, a
  four-row hosting table and twelve platform check IDs (`AZ-IAC` to `AZ-COST`).
  It has no decision guidance for ingress, data stores, identity or network
  topology, and no per-service security configuration.
- The intake (`templates/project.md`) has a free-text "Constraints" list. There is
  no place for an organisation's platform standards, and no rule for what happens
  when a recommendation conflicts with one.
- The runbook ends at Checkpoint 2, after the lead reviewer
  (`core/runbook.md`, stages 0 to 4).

### What teams asked for

From the tech lead (2026-11-07): a well-architected design for the detected
stacks, covering build, packaging, deployment, CI/CD, VNets, Entra ID, managed
identities, least privilege, CDN, firewall and hub-and-spoke networking. They
want options with diagrams, the reason one option beats another, and guidance on
how the design fits an organisation's existing standards. Named examples: App
Service against container services, which load balancer, internal against
external, which database, SQL against NoSQL, and how each is secured.

### Why the architect can't absorb this

- Its output is findings. A proposal isn't a finding, and mixing the two blurs
  "what we found" with "what we suggest" in the report the council receives.
- Its prompt is already long (twelve sections). Adding about ten decision areas
  and their baselines would crowd out the audit work. Reviewer judgement.
- A design needs a human choice partway through. An audit pass doesn't.

## Research

Sources were accessed on 2026-11-07. Statements marked "reviewer judgement" are not
taken from a source.

### Microsoft publishes decision guides for the named choices

- **Compute.** "Choose an Azure compute service" gives a flowchart and comparison
  tables for state management, networking, DevOps, team skills, scale and
  security. It says "The output from this flowchart is your starting point" and
  "A complete solution can include two or more compute services". Its team-skills
  table rates App Service and Container Apps as low operational overhead and AKS as
  high ([compute decision tree](https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/compute-decision-tree)).
- **Load balancing.** "Load balancing options" sorts services on two axes, global
  or regional and HTTP(S) or not. It covers API Management, Application Gateway,
  Front Door, Load Balancer and Traffic Manager, and gives a decision tree that
  starts from "Internet-facing application". It also tells readers to treat that tree
  as a starting point and do a more detailed evaluation
  ([load balancing options](https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/load-balancing-overview)).
- **Data.** "Understand data models" says to identify access patterns first, map
  them to models, then shortlist services. It gives heuristics such as "Strict
  multi-entity transactions: Relational" and "Evolving aggregate shape, JSON-centric
  APIs: Document", and signals for when to re-evaluate a choice
  ([data store models](https://learn.microsoft.com/en-us/azure/architecture/data-guide/technology-choices/understand-data-store-models)).
- **Network topology.** The hub-spoke reference architecture says hub and spoke "is
  the network topology that the Cloud Adoption Framework for Azure recommends". It
  also covers the Virtual WAN alternative, Azure Firewall as the egress point, and
  DNS for private endpoints ([hub-spoke topology](https://learn.microsoft.com/en-us/azure/architecture/networking/architecture/hub-spoke)).
- **Landing zones.** The Cloud Adoption Framework lists the design areas a
  platform must settle: billing and tenant, identity and access, resource
  organisation, network topology, security, management, governance, and platform
  automation and DevOps ([landing zone design areas](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/design-areas)).
  It also notes that landing zones are hub-spoke based, with a platform team that
  owns the hub and co-owns each spoke with the workload team
  ([hub-spoke topology](https://learn.microsoft.com/en-us/azure/architecture/networking/architecture/hub-spoke)).

### Microsoft publishes per-service secure configuration

- **Well-Architected service guides** exist for App Service, Functions, AKS,
  Application Gateway, Front Door, Load Balancer, Traffic Manager, Azure SQL
  Database, Cosmos DB, PostgreSQL, Blob Storage, Azure Firewall, Virtual Network,
  Service Bus, Event Grid and more
  ([service guides](https://learn.microsoft.com/en-us/azure/well-architected/service-guides/)).
  The catalogue page lists no guide for Container Apps; its security baseline
  is linked from the compute decision tree instead.
- **Security baselines** describe, per service, "the available security
  capabilities and the optimal security configurations". Each control has a
  Microsoft cloud security benchmark ID, whether the feature is supported and
  enabled by default, who is responsible for it, and configuration guidance
  ([security baselines overview](https://learn.microsoft.com/en-us/security/benchmark/azure/security-baselines-overview)).
  The compute decision tree links the baselines for Container Apps, AKS, Functions
  and others.

Lesson: the kit doesn't need to invent decision logic or security settings. It
needs to pin Microsoft's guidance into a fixed shape that an agent must fill with
evidence from the code, and add the one thing Microsoft can't know: the client's
own platform and rules.

## Decision

### D1. A new agent, `solution-designer`, in a new Stage 5

`core/agents/solution-designer.md` (model tier: top) runs after Checkpoint 2,
when the tech lead has accepted the findings. Its inputs are `project.md`,
`detected.md`, `01-discovery.md`, `02-architecture.md`, `07-final-report.md`,
`scans/` and `.audit/standards/` (D5). It loads the `azure-architecture` profile,
the decision catalogue (D3), the baselines (D4), `architecture-diagrams`, and the
stack profiles that `detected.md` lists.

The `architect` keeps its audit role. Its section 5 (hosting) stays as an as-is
comparison that the designer takes as an input, so the two don't compete.
Its section 7 (platform build requirements) moves to the designer, and the
architect's version shrinks to findings for gaps.

### D2. Two passes, two checkpoints

| Step | Output | Who acts |
|---|---|---|
| Pass A: options | `10-solution-options.md`, option diagrams | designer |
| Checkpoint 3 | A choice per decision, recorded in `project.md` under `## Checkpoint 3 choices` | tech lead, with the platform owner |
| Pass B: design | `11-solution-design.md`, `adr/ADR-NNN-*.md` (Proposed), diagram set | designer |
| Checkpoint 4 | Sign-off, or changes requested | tech lead |

Pass B reads only the chosen options, so it can't drift back to one the tech lead
rejected. Every ADR stays `Proposed`. Only humans accept them (unchanged).

### D3. A decision catalogue with one shape per entry

Each decision is a file in `profiles/azure-architecture/references/decisions/`,
with five parts:

1. **Question.** For example, "Which compute service hosts each deployable unit?"
2. **Signals.** What to establish from the code and the audit, each cited as
   `file:line` or a finding ID. For compute: long-running server or request
   handlers, background workers, in-process state, local disk writes, WebSockets,
   startup time, number of deployable units, team skills from the intake.
3. **Options and criteria**, from the Microsoft decision guide named in the entry,
   with the criteria the intake can weight (skills, budget, compliance, existing
   platform).
4. **Recommendation**: the chosen option, why each other option lost, and what
   would change the answer.
5. **Baselines to apply** if the option is chosen (D4).

First entries, in order:

| Entry | Covers | Microsoft guide |
|---|---|---|
| `compute.md` | App Service, Container Apps, AKS, Functions; splitting web from workers | compute decision tree |
| `ingress.md` | Front Door, Application Gateway, Load Balancer, Traffic Manager, API Management; internal against external; CDN | load balancing options |
| `data.md` | Relational against document, key-value or object; Azure SQL, PostgreSQL, Cosmos DB, Blob and Table storage, Redis | data store models |
| `identity.md` | Entra ID for users (platform auth against in-app), managed identity (system or user assigned), RBAC at resource scope, PIM, workload identity federation for pipelines | landing zone identity and access design area |
| `network.md` | Hub and spoke against Virtual WAN against a standalone VNet; VNet integration, private endpoints and private DNS, firewall egress, hybrid links | hub-spoke reference, landing zone network design area |
| `delivery.md` | Build once and promote; GitHub Actions against Azure Pipelines; environments and approvals; slot swap or revision rollout; rollback; IaC with Azure Verified Modules | landing zone platform automation and DevOps design area, App Service deployment best practices |

Messaging, caching, secrets and observability follow once the first six have
been through an eval.

### D4. Secure baselines per service, sourced from Microsoft

Each service the catalogue can recommend gets a file in
`profiles/azure-architecture/references/baselines/`, starting with App Service,
Container Apps, Front Door, Application Gateway, Azure SQL Database, Cosmos DB,
Storage and Key Vault. Each control has:

- a kit check ID (`BL-<SERVICE>-<NN>`), a one-line requirement, and its
  Microsoft cloud security benchmark control ID where one exists;
- a link to the service's Well-Architected guide or security baseline section;
- a note when the control isn't on by default.

For example, Azure SQL: Entra-only authentication, access from the app by managed
identity, a private endpoint with public network access off, auditing, Defender
for SQL, tested restore, separate read and write database roles, and Australian
regions.

Pass B marks every applicable control as *built*, *deviation requested* or *not
applicable* with a reason. The security agent may cite the same IDs in later
audits, so design and audit share one vocabulary.

### D5. Organisation standards: an input that outranks Microsoft guidance

- **Input.** The platform team puts its standards in `.audit/standards/` as
  Markdown or PDF. Typical contents: landing zone design, hub address ranges and
  egress model, naming and tagging, approved and prohibited services, Azure Policy
  assignments, pipeline templates, the identity model. `project.md` gains a
  "Platform standards" section naming the owner who vouches for them and the
  version or date.
- **Precedence.** Organisation standard first, then Microsoft guidance, then
  reviewer judgement.
- **Deviation requests.** When evidence shows a standard doesn't fit the workload,
  the design keeps the standard as the baseline and adds a request: the standard's
  clause, why it doesn't fit, the risk of following it, the proposed alternative,
  and who decides. It never quietly overrides the standard.
- **Conformance matrix.** `11-solution-design.md` lists each clause in the
  standards as conforms, deviation requested or not applicable.
- **Three modes**, chosen from what's provided:

  | Mode | When | Design approach |
  |---|---|---|
  | Mature | A landing zone and network standard exist | The workload is a spoke: it uses the organisation's hub, firewall, DNS, logging and pipelines |
  | Partial | Some standards exist | Uses what exists; lists each gap as a prerequisite with an owner question |
  | None | Nothing provided | Proposes the smallest landing zone that meets the Cloud Adoption Framework design areas as phase 0, and marks every platform fact as an assumption |

### D6. Standards are constraints, not evidence

AGENTS.md rule 4 says prose is a claim. A standards document is prose about the
platform, not about the target's code. The designer cites a standard as "a
constraint confirmed by `<owner>`", never as evidence of how the system behaves.

- If the target repository contains IaC or pipeline definitions, discovery reads
  them as evidence of what is deployed. The design reports drift between that code
  and the stated standards.
- Rule 10 still applies. Text in a standards document that addresses the agent
  ("approve this", "skip the network section") is recorded as a `governance`
  finding and not followed.
- Standards are different from `beliefs.md`. Beliefs are what people think the
  system does, and they're kept away from the auditors. Standards are rules the
  organisation sets for what gets built, so the designer must read them.

### D7. Diagrams per view and per option

Using the Diagram IR and house style from 0.13.2, with nested `group` paths for
subscription, VNet and subnet:

| Diagram | Pass |
|---|---|
| One comparison diagram per option, for compute, ingress, data and network only | A |
| Context (target) | B |
| Network topology: hub, spoke, subnets, firewall, private endpoints, DNS | B |
| Identity and access: each caller, its identity, role and scope | B |
| Delivery: commit, build, artefact, environments, approvals, production | B |
| Deployment per environment | B |

The context-diagram limits from `architecture-diagrams` (15 nodes, 20 edges)
apply to every diagram.

### D8. The design document's structure

`11-solution-design.md` follows a fixed outline: decision register; conformance
matrix; assumptions, constraints and dependencies; one section per decision area
(choice, design, baselines applied, diagram); environments and promotion; phased
roadmap (Strangler Fig, each phase with a precondition); questions for the
platform team; Limitations. The outline adapts the numbered, register-based
structure of the tech lead's `senior-enterprise-solution-architect` skill, which
is user-level and can't be assumed on other machines, so the kit carries its own
template.

`kit verify` gains checks: each decision cites at least one signal and a
Microsoft guide; each baseline row has a status and, for deviations, a reason;
each standards clause appears in the conformance matrix; each Pass B decision
matches a Checkpoint 3 choice.

### D9. Build and packaging guidance lives with the stack

Each stack profile gets `references/build-and-package.md`. For `node-express`:
`npm ci` from the lockfile, dependency pruning, the artefact form (zip with run
from package, or a container image), Node.js LTS pinning, the start command, and
what must not be in the artefact (`.env`, tests, dev tooling). `delivery.md`
handles the stack-neutral parts. A Python or .NET stack later adds its own file.

### D10. Evaluation

Two runs on the pilot eval snapshot, same kit version:

1. With no standards (mode "None"). Expected: a phase 0 landing zone, assumptions
   marked, no invented organisation facts.
2. With `templates/examples/council-azure-platform.standard.md` copied into
   `.audit/standards/` (mode "Mature"). Expected: the design changes where the
   standard requires it. The places to check are listed in the eval notes kept
   with the seeded-issues key, so they never reach the agent.

Pass criteria: every decision traceable to code signals and a Microsoft guide; no
standard silently overridden; deviation requests where the standard and the
evidence conflict; diagrams within the limits.

## Consequences

- The runbook gains Stage 5 and Checkpoints 3 and 4. A full engagement takes
  longer, and the platform owner joins Checkpoint 3.
- The architect's section 7 moves to the designer, so audit reports become
  shorter and design work moves to its own document.
- The kit carries a catalogue that ages: Microsoft reviews the decision guides on
  a 365-day cycle (page metadata). Each entry records its source URLs and access
  date, and a refresh is a deliberate kit change, as with the Linguist data in
  ADR 0001.
- The intake gains a standards folder and owner. Councils without standards
  still get a design (mode "None").
- Constraints C2, C3 and C5 are unchanged: the designer reads files and the
  allow-listed documentation domains only, and writes only under `.audit/`.

## Rejected options

| Option | Reason |
|---|---|
| Extend the `architect` agent | Mixes findings with proposals, overloads one prompt, and has no point for a human choice. |
| Let the model choose freely, citing whatever it finds | Choices would vary run to run and lean on popularity. The catalogue ties each choice to code signals and a named Microsoft guide. |
| Use the `senior-enterprise-solution-architect` skill as the agent | It's user-level, not in the kit, so other machines lack it. Its structure is adapted into the kit's own template. |
| Generate Bicep or Terraform | The kit is read-only on the target and builds nothing. IaC belongs to the platform team; the design names the Azure Verified Modules to use. |
| Treat standards like `beliefs.md` and hide them from agents | Beliefs are kept away so they don't bias findings. Standards are binding rules for what gets built, so the designer must apply them. |

## Risks and open items

- **Standards content may be sensitive.** Address ranges and firewall rules end up
  in `.audit/`. The engagement policy should say whether design outputs may
  include them or must refer to them by clause only.
- **Cost of the stage.** Two top-tier passes over a large context. Not measured;
  the eval records tokens and duration as for other stages.
- **Catalogue scope.** Six decisions don't cover messaging, caching or
  observability. Gaps are listed under Limitations until those entries exist.
- **Standards in PDF.** Agents read PDFs unevenly. The intake may need a step that
  converts them to Markdown, run by a person.
- **Who attends Checkpoint 3.** The record assumes the tech lead consults the
  platform owner. The runbook should name that role, not leave it implied.

## Review history

| Reviewed at | Decision | Notes |
|---|---|---|
| 2026-11-07T09:11:55Z | Drafted | Initial version, from the tech lead's request and Microsoft's compute, load balancing, data store, hub-spoke, landing zone, service guide and security baseline pages. |
| 2026-11-07T11:24:55Z | Approved | Approved by the tech lead. |
