# Salesforce Clouds — Taxonomy

Controlled vocabulary for the **Salesforce cloud(s)** a project, REQ, or bug touches. Used by `/init` (to set `salesforce.clouds:` in `.adlc/config.yml`), by `/spec` (to tag REQs with `sf_cloud:`), and by reviewer agents to branch on cloud-specific patterns (e.g., FSC's compliance-heavy data model vs. Sales Cloud's CRM patterns).

**This file is the canonical source.** `/init` copies it into the consumer repo's `.adlc/context/sf-clouds.md`; the consumer is free to trim entries that are not in scope but should not invent new keys without updating this file in the toolkit.

**Sources.** Cloud descriptions are derived from publicly available Salesforce documentation (help.salesforce.com, trailhead.salesforce.com, salesforce.com product pages). India-specific notes draw on publicly available regulator/standard publications (RBI, SEBI, IRDAI, TRAI, MeitY, DPDP Act 2023, ABDM, GSTN, MoHFW, CDSCO, NHA). Treat them as orientation, not legal advice — verify against current circulars at REQ time.

---

## How to use this taxonomy

- **`clouds` is an array.** A project is rarely "just Sales Cloud" — it almost always layers Platform + (Sales | Service) + (Experience | Data Cloud | Agentforce | …). Pick every cloud the project actually deploys metadata into or integrates with at runtime.
- **An industry cloud (FSC, CG, Comms, etc.) implies its base clouds.** If you select `financial-services-cloud`, you do NOT also need `sales-cloud` and `service-cloud` unless you want reviewer agents to weight CRM-only patterns equally with FSC-specific ones. Default: list the industry cloud and the base clouds it materially extends.
- **OmniStudio, Data Cloud, Agentforce are cross-cloud.** They are listed here as first-class entries; pick them in addition to whichever industry/base cloud uses them.
- **Slack and MuleSoft are out of scope for this toolkit's metadata pipeline** but are listed for context-tagging only — projects that touch Slack workflows or MuleSoft contracts should still tag the REQ.

---

## Core clouds (every project has ≥1)

### `platform` — Lightning Platform (Force.com)
The metadata-driven app platform underneath every other cloud: Apex, Flow, LWC, Custom Objects, Permission Sets, Sharing, FlexiPages, App Builder, Lightning App. Always selected — even pure FSC/Health Cloud projects deploy Platform metadata.

**India context.** DPDP Act 2023 consent-capture custom objects, `Person Account` privacy semantics, residency considerations for Hyperforce-India (BOM/IND2) pods.

### `sales-cloud` — Sales Cloud
Lead → Opportunity → Account/Contact CRM. Forecasting, Pipeline Inspection, Sales Engagement, Einstein Activity Capture, Territory Management, Enablement (myTrailhead), Revenue Cloud (CPQ + Billing).

**India context.** GSTIN on Account, B2B vs B2C distributor hierarchies, Bharat-tier SMB segmentation.

### `service-cloud` — Service Cloud
Case → Entitlement → SLA → Knowledge → Omni-Channel routing. Service Console, Field Service, Voice (with Amazon Connect / partner CTI), Messaging for In-App / WhatsApp / SMS, Knowledge, Survey.

**India context.** WhatsApp Business API integrations (Meta + BSP), DLT/TRAI commercial-communication compliance for SMS, regional-language Knowledge (Hindi + 22 scheduled languages), Aadhaar-redacted case attachments.

### `experience-cloud` — Experience Cloud (formerly Communities)
External-facing sites/portals on Salesforce Sites, Aura, LWR (Lightning Web Runtime), or Mobile Publisher. Used for partner portals, customer self-service, dealer/distributor networks, public help-centers.

**India context.** Multi-language (Hindi, Tamil, Telugu, Bengali, Marathi…) sites, Aadhaar/DigiLocker login via Auth Provider, Razorpay/PhonePe/UPI checkout via Apex callouts.

---

## Marketing & engagement clouds

### `marketing-cloud-engagement` — Marketing Cloud Engagement (formerly ExactTarget)
Journey Builder, Email Studio, Mobile Studio (SMS, push, WhatsApp), Automation Studio, Content Builder, Audience Builder, AMPscript / SSJS / GTL.

**India context.** DLT (Distributed Ledger Technology) registration of templates with TRAI for SMS, sender-ID whitelisting, CDA (Consent Data Architecture) integration, RBI Sec 5(b) for unsolicited financial communications.

### `marketing-cloud-account-engagement` — Account Engagement (formerly Pardot)
B2B marketing automation: Engagement Studio, Forms, Landing Pages, Prospect, lead scoring/grading.

### `marketing-cloud-personalization` — Personalization (formerly Interaction Studio)
1:1 web/email personalization, recipes, templates, Einstein Recipes.

### `marketing-cloud-intelligence` — Intelligence (formerly Datorama)
Marketing-data ETL + dashboarding. Often replaced by Tableau Cloud for new builds.

### `marketing-cloud-growth` — Marketing Cloud Growth / Advanced Editions
Newer Data Cloud-native marketing edition (Growth, Advanced). Selected in addition to (or instead of) the Engagement edition for greenfield Data Cloud-first projects.

**India context for all marketing clouds.** DPDP Act 2023 consent purposes, "right to be forgotten" purge across DMOs, child-data restrictions (under-18), TRAI commercial-communication classes, opt-in/opt-out audit trail.

---

## Commerce clouds

### `commerce-cloud-b2c` — B2C Commerce (formerly Demandware)
Storefront Reference Architecture (SFRA), Page Designer, OCAPI, SCAPI, B2C Headless, Composable Storefront, Einstein for Commerce.

**India context.** Multi-currency catalogs (INR/USD/AED), GST-inclusive vs exclusive pricing, COD support, Razorpay/Cashfree/PhonePe/UPI Intent flow, ONDC catalog interop (publicly published spec).

### `commerce-cloud-b2b` — B2B Commerce / B2B2C (Lightning B2B)
Native B2B storefronts on the platform. Buyer Group, Account Hierarchy pricing, contract pricing, reorder, quote.

### `commerce-cloud-d2c` — Direct-to-Consumer (D2C subset of B2C)
Often co-tagged with `commerce-cloud-b2c` on Indian DTC builds (FMCG, beauty, apparel).

### `revenue-cloud` — Revenue Cloud (CPQ + Billing + Subscription Management)
Configure-Price-Quote, contract amendment, usage billing, dunning, revenue recognition.

**India context.** GST (CGST/SGST/IGST) tax engines, e-invoice generation against IRP (Invoice Registration Portal), TDS/TCS withholding, INR rounding rules.

---

## Data, AI & analytics clouds

### `data-cloud` — Data Cloud (formerly CDP / Customer 360 Data)
DLO (Data Lake Object) → DMO (Data Model Object) → Calculated Insights → Identity Resolution → Segments → Activations. Zero-Copy to Snowflake/Databricks/BigQuery, Vector DB, BYOM.

**India context.** Data residency (Hyperforce-India BOM/IND2 pods), DPDP Act 2023 fiduciary obligations, RBI sectoral data-localization for payments (CCAvenue/Razorpay tokens MUST stay in-country), Account Aggregator framework data flows.

### `agentforce` — Agentforce (Employee Agent / Service Agent / Sales Agent)
Topic → Action → Plan → Reasoning Engine. Atlas Reasoning, Prompt Builder, Model Builder, BYO LLM. Agent Studio. Requires API 66.0+.

**India context.** Hindi + regional-language prompt grounding, BharatGPT/Sarvam BYO-LLM patterns, RBI-compliant agent-driven loan origination decisioning constraints, audit trail for regulated industries.

### `tableau-cloud` — Tableau Cloud / Tableau Pulse
Hosted Tableau, Pulse for AI summaries, Tableau Embedded.

### `crm-analytics` — CRM Analytics (formerly Tableau CRM, Einstein Analytics)
Native analytics inside Salesforce — datasets, lenses, dashboards, Einstein Discovery.

### `einstein-1-platform` — Einstein 1 / Einstein Platform
Predictions, NBA, classification models, vector search, sentiment, Trust Layer.

---

## Industry clouds

### `financial-services-cloud` — Financial Services Cloud (FSC)
Banking, Wealth Mgmt, Insurance data model: Financial Account, Financial Goal, Householding, Action Plans, Insurance Policy, Claim, Distributor Performance Mgmt. Built on Platform + Sales/Service Cloud.

**India context.** RBI Digital Lending Guidelines (Sept 2022 + 2023 amendments), Account Aggregator framework (Sahamati) data-fetch flows, KYC/CKYC/v-CKYC, DigiLocker income-proof, UPI-Autopay mandates, NACH, Nominee mgmt under PMLA, IRDAI policy-issuance & claims, SEBI KYC for wealth, NPCI's UPI 2.0 for collection.

### `health-cloud` — Health Cloud
Patient, Care Plan, Care Team, EHR Sync (HL7/FHIR), Consent, Provider Network, Utilization Mgmt.

**India context.** Ayushman Bharat Digital Mission (ABDM) — ABHA address, HFR (Health Facility Registry), HPR (Healthcare Professional Registry), Unified Health Interface (UHI). Ayushman Bharat PMJAY claim flows. Telemedicine Practice Guidelines 2020 (MoHFW). Hospital empanelment under CGHS/ECHS.

### `life-sciences-cloud` — Life Sciences Cloud (formerly part of Health Cloud + Vlocity Health)
Clinical Trial Mgmt, Patient Services, Field Medical (MSL), Adverse Event capture, HCP/HCO 360.

**India context.** CDSCO regulations, New Drugs and Clinical Trials Rules 2019, Schedule Y, CDSCO SUGAM portal interop, IPC adverse-event reporting (PvPI), DCGI approval workflows, Pharmaceutical Tracking & Tracing for exports.

### `communications-cloud` — Communications Cloud (CME — Comms / Media / Energy)
CSP-grade product catalog (Enterprise Product Catalog, EPC), CPQ for telco, Order Mgmt, Industry Console, ESM, OCS — built on OmniStudio + Vlocity heritage.

**India context.** TRAI's Mobile Number Portability (MNP) flows, DoT compliance, Aadhaar-based eKYC for SIM activation (post-DoT amendments), Bharat Net B2B circuits, 5G NSA/SA service-catalog modeling, Indian Telecom Bill 2023 obligations.

### `media-cloud` — Media Cloud (M part of CME)
OTT/broadcast publisher patterns, advertising sales, audience segmentation, content licensing.

**India context.** TRAI's broadcasting & cable services regulation, NTO (New Tariff Order) channel pricing, BARC ratings ingest, MIB self-regulation reporting.

### `energy-and-utilities-cloud` — Energy & Utilities Cloud (E part of CME)
DISCOM/Genco/Transco data model, Premise/Service Point/Meter, Utilities Connect, outage mgmt, contract & billing.

**India context.** Discom-tier (state-utility) tariff hierarchies, Smart Meter National Programme rollout, UDAY-scheme reporting, MoP/CERC compliance, KUSUM solar-pump enrollment, time-of-day tariff structures.

### `manufacturing-cloud` — Manufacturing Cloud
Sales Agreement, Account-Based Forecasting, Run-Rate Forecast, Rebate Mgmt, Service Console for Mfg, Quote-to-Cash with revenue cloud.

**India context.** PLI (Production-Linked Incentive) scheme reporting, GST e-invoicing, MSME-supplier reporting (TReDS interop), Digital Supply Chain (DSCM) hooks for Indian conglomerate-tier hierarchies (House of Tata, Mahindra, Reliance group structures).

### `consumer-goods-cloud` — Consumer Goods Cloud (CG Cloud)
Retail Execution (offline + online), Visit Planner, Trade Promotion Mgmt (TPM), Order Mgmt, Mobile-Offline for field reps.

**India context.** General Trade (Kirana) vs Modern Trade segmentation, Wholesaler-Distributor-Retailer hierarchies, GST e-way bill on secondary sales, ONDC catalog publication for D2C arms, regional-language SKU labeling, beat-plan modeling for 12M+ Kirana universe.

### `automotive-cloud` — Automotive Cloud
OEM-Dealer-Customer 360, Vehicle, Driver, Household, Service, Connected Vehicle, Lead-to-Delivery, Trade-In, Warranty.

**India context.** VAHAN/SARATHI integration for RC, Insurance & PUC, FASTag account linking, BS-VI emission compliance metadata, dealer DMS interop (TVS-DMS, Excelon, Autoline), EV battery-warranty separate-policy modeling, Vehicle Scrappage Policy enrollments.

### `public-sector-solutions` — Public Sector Solutions (PSS)
License Permits Inspections (LPI), Benefits Mgmt, Grants Mgmt, Case Mgmt, Constituent 360, Regulatory Compliance.

**India context.** State e-District portals, DigiLocker integration, Aadhaar e-KYC under UIDAI's Section 7/Section 4 entitlements, e-Governance MoSPI standards, NIC infra co-existence patterns, Aapke Dwar Sarkar / CM-helpline call-center routing.

### `education-cloud` — Education Cloud (formerly EDA)
Student 360, Recruitment & Admissions Connect, Advising, Alumni Engagement, Education Data Architecture (EDA) base.

**India context.** UGC/AICTE compliance reporting, NEP 2020-aligned credit-bank (ABC — Academic Bank of Credits), DigiLocker degree issuance, Samarth ERP coexistence in central universities.

### `nonprofit-cloud` — Nonprofit Cloud (NPC, formerly NPSP)
Donor, Gift, Recurring Donation, Program Mgmt, Outcome Mgmt, Volunteer Mgmt.

**India context.** FCRA (Foreign Contribution Regulation Act) reporting, 12A/80G receipt issuance, CSR Section 135 spend tracking against Form CSR-2, SBI FCRA-account requirement.

### `net-zero-cloud` — Net Zero Cloud
Scope 1/2/3 emissions accounting, supplier sustainability, audit trail, SBTi/CDP reporting.

**India context.** BRSR (Business Responsibility & Sustainability Report) — top-1000 listed-company SEBI mandate, PAT (Perform-Achieve-Trade) scheme reporting, India's NDC alignment.

### `loyalty-management` — Loyalty Management
Programs, Tiers, Points, Vouchers, Promotions, Member 360.

**India context.** Co-branded credit card tie-ins, RBI's recent rules on payment-aggregator-led rewards, GST treatment of point-redemptions.

### `consumer-goods-cloud` / `retail` cross-tag — Retail Execution
For pure-play retail beyond CG (apparel, QSR, pharmacy chains), tag with `consumer-goods-cloud` AND `commerce-cloud-b2c` if there is a digital storefront.

---

## Cross-cloud capability layers

### `omnistudio` — OmniStudio (formerly Vlocity Components)
OmniScript, FlexCard, DataRaptor, Integration Procedure, Calculation Procedure, Industry Process Library. Used as the UX/orchestration layer in **every Industries Cloud** (FSC, Health, Comms, Media, E&U, PSS, Energy & Utilities). Often co-deployed with Sales/Service Cloud builds even outside Industries.

### `mulesoft` — MuleSoft Composer / Anypoint (cross-toolkit)
RAML/OAS contracts, Mule 4 apps, Anypoint MQ/Exchange. Tag REQs whose Salesforce side calls a Mule API contract — the actual Mule artifact lives in `adlc-toolkit-mulesoft`.

**India context.** API gateway patterns for ONDC, Account Aggregator, ABDM, UPI Switch.

### `slack` — Slack (Salesforce-owned platform)
Slack Connect, Slack Workflow Builder, Slack-First selling/service, Salesforce-Slack Channel sync.

### `heroku` — Heroku (Salesforce Platform-as-a-Service)
Long-running async, Postgres, Redis, Connect to push Salesforce data out.

### `field-service` — Field Service (formerly FSL)
Service Appointment, Resource Absence, Polygon-based dispatch, Mobile (online/offline), Optimization Engine.

**India context.** Bharat-tier 2/3 connectivity-resilient mobile mode, Hindi/regional UI, two-wheeler vs four-wheeler resource-vehicle modeling, hyperlocal SLA windows.

### `commerce-cloud-payments` / `payments` — Salesforce Payments (Payment Platform)
Embedded payments across Commerce + Service.

**India context.** Razorpay / PhonePe / Cashfree / Paytm / BillDesk gateway adapters, RBI's payment-aggregator licensing landscape, UPI Intent vs Collect flows.

---

## Selecting clouds at `/init`

`/init` will ask the user (via `AskUserQuestion`) which clouds are in scope. The user picks one or more keys from the list above. The chosen keys are written to `.adlc/config.yml` under `salesforce.clouds:` and into `.adlc/context/sf-clouds.md` as a header annotation showing "selected clouds".

Subsequent skills and reviewer agents read `salesforce.clouds:` to:
- Branch on cloud-specific patterns (FSC compliance gates vs. plain Sales Cloud).
- Route REQ retrieval to lessons tagged with the same cloud.
- Skip industry-specific quality rules when an industry cloud is not selected.

If a REQ touches a cloud not in the project's `salesforce.clouds:` list, `/spec` should warn and require either (a) adding the cloud to the project config or (b) confirming a one-off integration without persistent ownership.
