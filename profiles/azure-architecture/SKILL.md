---
name: azure-architecture
description: Use when evaluating hosting, platform or architecture on Microsoft Azure against the Azure design principles, cloud design patterns, the Well-Architected Framework, landing zones, Azure Verified Modules and build-once-deploy-many delivery.
---

# Azure architecture profile

## Sources
- Design principles (primary lens): https://learn.microsoft.com/en-us/azure/architecture/guide/design-principles/
- Cloud design patterns: https://learn.microsoft.com/en-us/azure/architecture/patterns/
- Well-Architected Framework: https://learn.microsoft.com/en-us/azure/well-architected/
- Landing zones: https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/
- Azure Verified Modules: https://azure.github.io/Azure-Verified-Modules/
- App Service deployment best practices: https://learn.microsoft.com/en-us/azure/app-service/deploy-best-practices
- Front Door origin lock-down to App Service: https://learn.microsoft.com/en-us/azure/frontdoor/origin-security

## 1. Design principles scorecard
Score each principle Applied / Partial / Not applied / N/A, with evidence.
CHECK-IDs for findings:

| CHECK-ID | Principle |
|---|---|
| AZ-SELF-HEALING | Design for self-healing (retries, health checks, graceful degradation) |
| AZ-REDUNDANCY | Make all things redundant (instances, zones, region pairing as the business needs) |
| AZ-MIN-COORDINATION | Minimise coordination (no shared in-process state, idempotent operations) |
| AZ-SCALE-OUT | Design to scale out (stateless instances) |
| AZ-PARTITION | Partition around limits |
| AZ-OPERATIONS | Design for operations (telemetry, alerts, runbooks) |
| AZ-MANAGED | Use managed services |
| AZ-IDENTITY | Use an identity service (Entra ID, managed identity; no shared secrets) |
| AZ-EVOLUTION | Design for evolution (seams, contracts, versioning) |
| AZ-BUSINESS | Build for the needs of the business (RTO/RPO and SLOs agreed with the owner) |
| AZ-FMA | Failure mode analysis done for every dependency |

## 2. Patterns. Recommend only for an evidenced problem
Retry + Circuit Breaker (downstream APIs); Queue-Based Load Leveling (accept
requests while downstream is down); Claim Check / Valet Key (large uploads via
Blob Storage); Anti-Corruption Layer (isolate a vendor's data model); Health
Endpoint Monitoring; Gateway Offloading (WAF, TLS, rate limits at the edge);
Strangler Fig (incremental replacement).

## 3. Hosting options to compare for web workloads
| Option | Fits when | Watch for |
|---|---|---|
| App Service | Long-running server, needs slots, VNet integration, shared `/home` storage | Shared storage tempts state; scale-out with in-process state |
| Container Apps | Stateless containers, separate workers or jobs, scale to zero | Ephemeral disk; team needs container skills |
| Static Web Apps + Functions | Static front end, stateless API handlers | Usually means a rewrite for a server app |
| AKS | Many services with a platform team to run them | Rarely right for a small team |
Criteria: how the app *actually* runs (from discovery's State section),
uploads, private networking, managed identity, WAF, deployment safety and
rollback, cost, and the team's ability to operate it.

## 4. Platform build requirements (feed the architect's section 7)
| CHECK-ID | Requirement |
|---|---|
| AZ-IAC | All resources defined as code (Bicep or Terraform), using Azure Verified Modules where one exists. No changes made in the portal |
| AZ-BUILD-ONCE | One immutable build artefact promoted dev → test → prod. Environments differ only by parameters (`.bicepparam` / app settings), never by rebuilding |
| AZ-ENV-ISOLATION | Each environment has its own resources and backing services. No test traffic reaches production data stores or document libraries |
| AZ-DEPLOY-SAFETY | Staging slot (or revision), smoke test, approval, swap; rollback documented and rehearsed |
| AZ-SECRETS | Key Vault with managed identity; no secrets in plain app settings or the repo |
| AZ-EDGE | Front Door or Application Gateway with WAF in prevention mode; origin accepts traffic only from the edge (service tag + `X-Azure-FDID` check, or Private Link) |
| AZ-NETWORK | Private endpoints or VNet integration for data and internal services; hybrid connectivity documented |
| AZ-OBSERVABILITY | Application Insights / Log Analytics, availability tests, alerts on failure paths, retention aligned with records policy |
| AZ-BACKUP | Backup and restore for every stateful resource, tested |
| AZ-REGION | Australian regions (Australia East / Southeast) for Australian public-sector data, unless an exception is recorded |
| AZ-LANDING-ZONE | Deployed into a governed subscription (Policy, central logging, identity, hub networking) or the gap recorded |
| AZ-COST | Right-sized SKUs, budgets and alerts, tags per environment |

## 5. Well-Architected pillars
Reliability, Security, Cost Optimisation, Operational Excellence,
Performance Efficiency. Findings for gaps only, tagged `WAF-<Pillar>`.

## ADR template
```
# ADR-NNN: <Title>
- Status: Proposed
- Date / Kit version / Commit:
- Context: the problem and constraints, with evidence and finding IDs
- Options considered: at least three, with pros and cons
- Decision: the recommended option
- Consequences: trade-offs, cost, skills, migration effort, what gets harder
- Sources: Microsoft Learn links
```

## Red flags
- Recommending a platform before establishing how the app actually runs
- Choosing patterns because they're fashionable, not because of evidence
- Ignoring the team's capacity to operate what you recommend
- "Build once, deploy many" claimed while each environment rebuilds the code
