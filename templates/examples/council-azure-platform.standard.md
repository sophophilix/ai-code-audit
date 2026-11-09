# Azure platform standard: Example Shire Council (sample)

> This is a fictional sample for evaluating the kit's solution design stage
> (ADR 0003). Example Shire Council doesn't exist, and every name, address range
> and identifier below is invented. Copy it into a workspace's `.audit/standards/`
> to test a design against a "mature" organisation standard.

| Field | Value |
|---|---|
| Owner | ICT Platform Lead, Example Shire Council |
| Version | 2.1 |
| Applies to | Every workload deployed to the council's Azure tenant |
| Keywords | "Must" is mandatory. "Should" needs a recorded reason to depart from it. "May" is optional. |

Each clause has an ID. A design must list every clause it relies on or departs
from, using these IDs.

## 1. Landing zone and resource organisation

- **LZ-01** Workloads must be deployed into the council's Azure landing zone. The
  management group hierarchy is `council` > `platform` | `landing-zones` >
  `corp` | `online` | `sandbox`.
- **LZ-02** A workload must have one subscription per environment: `dev`, `test`
  and `prod`. Non-production subscriptions sit under `landing-zones/corp` or
  `landing-zones/online` like production, never under `sandbox`.
- **LZ-03** Workloads that serve the public internet go under `online`. Workloads
  for staff only go under `corp`, which has no inbound internet path.
- **LZ-04** Subscriptions are created by the platform team through the
  subscription vending pipeline. Workload teams must not create subscriptions,
  management groups or policy assignments.
- **LZ-05** Resources must be deployed in Australia East. Australia Southeast is
  permitted for backup and disaster recovery copies only.

## 2. Network

- **NET-01** The council runs a hub-and-spoke network. The hub is in the
  `platform-connectivity` subscription, Australia East, address space
  `10.100.0.0/16`. It contains Azure Firewall Premium, the ExpressRoute gateway
  to the council data centre, Azure Bastion and the private DNS resolver.
- **NET-02** Each workload environment gets one spoke VNet, a `/22` allocated by
  the platform team from `10.110.0.0/14`. Workload teams must not choose their own
  address ranges.
- **NET-03** All spoke egress must route through the hub firewall (a user-defined
  route `0.0.0.0/0` to the firewall). Outbound destinations must be on the
  workload's firewall allow-list, requested through the platform team.
- **NET-04** Azure PaaS data services (SQL, Storage, Key Vault, Cosmos DB, Service
  Bus) must be reached through private endpoints in the workload spoke, with
  public network access disabled.
- **NET-05** Private DNS zones for private endpoints are owned by the platform
  team and linked to the hub. Workload teams must not create their own
  `privatelink.*` zones.
- **NET-06** App Service and Container Apps must use VNet integration into the
  spoke, so their outbound traffic follows NET-03.
- **NET-07** Access to on-premises systems (for example, line-of-business
  databases and the GIS server) is over ExpressRoute through the hub only. Hybrid
  Connections and site-to-site VPNs from a spoke are prohibited.
- **NET-08** Network security groups must be applied to every subnet, with an
  explicit deny-all rule at the lowest priority.

## 3. Ingress

- **ING-01** Internet-facing web workloads must be published through the shared
  Application Gateway WAF v2 in the `platform-ingress` spoke. The WAF runs in
  prevention mode with the OWASP Core Rule Set managed by the platform team.
- **ING-02** Azure Front Door may be used only with an approved exception (see
  section 10), for example where global caching is needed. If approved, the
  origin must accept traffic only from Front Door through Private Link.
- **ING-03** Workloads must not have a public endpoint other than through ING-01
  or an approved ING-02. App Service public access must be restricted to the
  Application Gateway subnet.
- **ING-04** Staff-only workloads must not be published to the internet. Staff
  reach them over the corporate network or the council's VPN.
- **ING-05** TLS 1.2 or higher. Certificates are issued by the platform team and
  held in the platform Key Vault.

## 4. Identity and access

- **IAM-01** Microsoft Entra ID is the only identity provider for staff. Workloads
  must not hold local staff accounts.
- **IAM-02** Workloads must authenticate to Azure services with managed
  identities. Client secrets and certificates for app registrations are
  prohibited for Azure-to-Azure access.
- **IAM-03** Where a workload calls a non-Azure API that needs an app
  registration, the credential must be a certificate stored in Key Vault, rotated
  at least every 12 months. Client secrets need an approved exception.
- **IAM-04** Role assignments for workload identities must be at the narrowest
  scope that works (resource, then resource group). Subscription-scope roles for
  workload identities are prohibited.
- **IAM-05** `Owner` and `User Access Administrator` are held only by the platform
  team. Workload teams receive `Contributor` on their resource groups in `dev`,
  and `Reader` in `test` and `prod`.
- **IAM-06** Human access to production write roles is through Privileged Identity
  Management, time-limited and approved.
- **IAM-07** Deployment pipelines must authenticate with workload identity
  federation (OIDC). Stored service principal secrets in pipelines are prohibited.

## 5. Compute

| Service | Status |
|---|---|
| App Service (Linux, Premium v3 or higher in `prod`) | Approved |
| Azure Container Apps (workload profiles environment, VNet integrated) | Approved |
| Azure Functions (Premium or Flex Consumption, VNet integrated) | Approved |
| Azure Kubernetes Service | Prohibited for workload teams; platform team only |
| Virtual machines | Exception only |

- **CMP-01** Production workloads must run at least two instances, spread across
  availability zones where the service supports it.
- **CMP-02** Container images must be built by the pipeline and stored in the
  platform Azure Container Registry. Public registries must not be pulled at run
  time.

## 6. Data

| Service | Status |
|---|---|
| Azure SQL Database | Approved, preferred for relational data |
| Azure Database for PostgreSQL Flexible Server | Approved |
| Azure Storage (Blob, Queue, Table) | Approved |
| Azure Cosmos DB for NoSQL | Approved with conditions: needs a data owner's sign-off and a cost estimate |
| Azure Managed Redis | Approved for cache and session state only, never as the system of record |
| Self-hosted databases | Prohibited |

- **DATA-01** Every data store must have a classification tag: `public`,
  `internal`, `sensitive` or `protected`.
- **DATA-02** Data must stay in Australian regions (LZ-05).
- **DATA-03** Azure SQL and PostgreSQL must use Microsoft Entra authentication
  only. SQL logins are prohibited.
- **DATA-04** Stores classified `sensitive` or `protected` must use
  customer-managed keys in the workload's Key Vault.
- **DATA-05** Backups must meet the workload's agreed recovery point and recovery
  time objectives, and a restore must be tested at least every six months.
- **DATA-06** Records must be kept in line with the council's records retention
  schedule. The application owner confirms the schedule for each data set.

## 7. Secrets and keys

- **SEC-01** One Key Vault per workload per environment, in RBAC mode, with purge
  protection on.
- **SEC-02** Secrets must not appear in app settings, pipeline variables or source
  code. App settings use Key Vault references.

## 8. Delivery

- **DEL-01** Pipelines run in the council's Azure DevOps organisation using the
  platform team's shared YAML templates. GitHub Actions is not approved for
  deployment to council subscriptions.
- **DEL-02** Infrastructure must be defined in Bicep using Azure Verified Modules
  where one exists. Portal changes in `test` and `prod` are prohibited.
- **DEL-03** One build artefact is promoted from `dev` to `test` to `prod`.
  Environments differ only by parameter files.
- **DEL-04** Production deployments need approval by the application owner and
  must use a staging slot or revision with a smoke test before traffic moves.
- **DEL-05** Dependencies are restored from the council's Azure Artifacts feed,
  which proxies the public registries.

## 9. Operations

- **OPS-01** Diagnostic settings send logs and metrics to the central Log
  Analytics workspace in `platform-management`. Azure Policy deploys them.
- **OPS-02** Every web workload has Application Insights, connected to the central
  workspace, and an availability test against its health endpoint.
- **OPS-03** Log retention: 90 days interactive, then archive to two years.
  Longer retention needs the records manager's approval.
- **OPS-04** Required tags: `owner`, `costCentre`, `environment`,
  `dataClassification`, `application`. Azure Policy denies resources without them.
- **OPS-05** Each subscription has a budget with alerts at 80% and 100%.
- **OPS-06** Names follow the Cloud Adoption Framework abbreviations, for example
  `app-<workload>-<env>-aue-001`.

## 10. Exceptions

A workload team that can't meet a clause raises an exception with the ICT Platform
Lead. It must state:

1. the clause ID;
2. why the clause doesn't fit the workload, with evidence;
3. the risk of meeting it and the risk of not meeting it;
4. the alternative proposed and any compensating controls;
5. how long the exception is needed.

Exceptions are approved by the ICT Platform Lead and, for security clauses, the
Information Security Officer. Approved exceptions are reviewed every 12 months.

## Azure Policy assignments (summary)

| Policy | Effect | Scope |
|---|---|---|
| Allowed locations: Australia East, Australia Southeast | Deny | `council` |
| Required tags (OPS-04) | Deny | `landing-zones` |
| Storage, SQL, Key Vault: public network access disabled | Deny | `landing-zones` |
| App Service: HTTPS only, minimum TLS 1.2, FTP disabled | Deny | `landing-zones` |
| Diagnostic settings to central workspace | DeployIfNotExists | `council` |
| Microsoft Defender for Cloud plans: App Service, SQL, Storage, Key Vault | DeployIfNotExists | `landing-zones` |
