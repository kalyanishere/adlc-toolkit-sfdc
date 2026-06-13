# Industry Domains — Taxonomy

Controlled vocabulary for the **business industry/domain(s)** a project, REQ, or bug serves. Used by `/init` to set `industry_domains:` in `.adlc/config.yml`, by `/spec` to tag REQs with `industry_domain:`, and by reviewer agents to weight industry-specific patterns (e.g., RBI guidelines on a lending REQ vs. SEBI-aligned KYC on a wealth REQ).

**Pair this with `sf-clouds.md`.** Salesforce Clouds describe *what platform capability* a project uses; Industry Domains describe *what business* the project serves. Both are arrays — a single project (e.g., a bank's wealth-mgmt arm using FSC + OmniStudio + Data Cloud) typically has ≥2 entries in each.

**Sources.** Industry descriptions and the India-specific anchors are derived from publicly available regulator/standard publications and industry-body sites — RBI, SEBI, IRDAI, NPCI, TRAI, MeitY, CDSCO, NMC, MoHFW, NHA/ABDM, GSTN, MoSPI, MoP/CERC, MoCA, MoCI, FSSAI, BIS, FAME-II, NHAI, MoRTH, Ministry of Education NEP 2020, AICTE, UGC, MoEFCC. Treat them as orientation, not legal advice.

---

## How to use this taxonomy

- **Pick all that apply.** A "BFSI" project at a universal bank typically tags `banking-retail`, `banking-corporate`, `wealth-management`, AND `insurance-life` if cross-sell is in scope.
- **Use the cross-cutting concerns at the bottom in addition to the industry,** not instead of it. `payments` is a cross-cut; `banking-retail` is an industry — most BFSI builds tag both.
- **Lesson retrieval is industry-aware.** When `/spec` retrieves prior lessons, an `industry_domain` match weights `+2` like `domain` does (see `taxonomy.md`).

---

## BFSI (Banking, Financial Services, Insurance)

### `banking-retail` — Retail Banking
Savings, current, FD, RD, sweep, debit card, retail loans (home, auto, personal, gold, education), CASA cross-sell, branch & digital onboarding.

**India context.** RBI's KYC Master Direction (latest 2024 amendment), V-CKYC, CKYCR upload, Aadhaar-OVD acceptance, UCIC mapping, Jan Dhan PMJDY accounts, BSBDA segment, NEFT/RTGS/IMPS, UPI Lite, central KYC registry, RBI Digital Lending Guidelines 2022/2023, FLDG arrangements, recovery & OTS norms, Sarfaesi for secured loans.

### `banking-corporate` — Corporate / Wholesale Banking
Cash mgmt, trade finance (LC/BG/Bills), supply-chain finance, working-capital, term loans, syndication, treasury & FX.

**India context.** SWIFT MX/MT migration (CBPR+), TReDS for MSME bill discounting, RBI Liberalised Remittance Scheme (LRS) for outward, FEMA reporting (R-Returns), AD-Cat-1 documentation, GIFT-IFSC offshore booking, FBIL benchmarks, EXIM-Bank refinance.

### `banking-sme` — SME / MSME Banking
Udyam-registered SME banking, working-capital, BL OD, business gold loan, GST-based credit assessment.

**India context.** Udyam Registration (Aadhaar-linked MSME), CGTMSE coverage for collateral-free, MUDRA Yojana (Shishu/Kishore/Tarun), SIDBI refinance, GSTR-1/3B-based cashflow underwriting, OCEN (Open Credit Enablement Network).

### `wealth-management` — Wealth & Private Banking
HNI/UHNI/family-office segmentation, portfolio mgmt (PMS, AIF), advisory, MF distribution, structured products, succession planning.

**India context.** SEBI RIA (Reg Inv Adviser), MFD distinction, AMFI registration, PMS Regulations 2020, AIF Cat-I/II/III, GIFT-IFSC fund vehicles, India-INX & NSE-IFSC, NRI/PIO/OCI account regimes, FATCA/CRS reporting via UBO.

### `capital-markets` — Capital Markets / Brokerage
Equity, F&O, currency, commodity, IPO/NFO, demat, custody, RTA.

**India context.** SEBI broker regs, NSE/BSE mkt-maker, NSDL/CDSL demat (BO ID), CKYC + e-Sign (Aadhaar) account opening, T+1 settlement, MTF margins, peak-margin rules, ASBA for IPOs, SCORES for grievances.

### `insurance-life` — Life Insurance
Term, ULIP, endowment, annuity, group-life, persistency mgmt, claims, surrender.

**India context.** IRDAI policy issuance, e-IA (e-Insurance Account) via NDML/CIRL/CAMS, Standard Term Saral Jeevan Bima, persistency 13/25/37/49/61M reporting, Bima Sugam (planned), agent licensing IC-38, point-of-sale-person (POSP) reg.

### `insurance-general` — General / Health / Motor Insurance
Motor (OD + TP), health (indemnity, top-up, OPD), travel, home, fire, marine, group health, weather/parametric, claims, surveyor.

**India context.** IRDAI motor TP-rate annual, FASTag-linked motor renewal, NHCX (National Health Claims Exchange) per ABDM, Ayushman Bharat PMJAY co-existence, cashless network, IBNR triangulation, motor TP pool, agriculture insurance under PMFBY.

### `insurance-reinsurance` — Reinsurance / Broking
Treaty, fac, retro, run-off, captive.

**India context.** GIC Re mandatory cession, IRDAI cross-border reinsurer (CBR) registration, GIFT-IFSC reinsurance branch.

### `payments` — Payments (cross-cut)
Acquiring, issuing, switch, gateway, aggregation, merchant onboarding, settlement, dispute.

**India context.** UPI (UPI 2.0, UPI Lite, UPI 123Pay, AutoPay, UPI-credit-line), NPCI rails (IMPS, AePS, NACH, BBPS, NETC FASTag, RuPay), RBI Payment Aggregator/Payment Gateway licensing, on-soil tokenization mandate, card-on-file tokenization, RuPay credit-on-UPI, e-RUPI prepaid voucher, CBDC retail/wholesale pilots, Bharat Bill Payment System (BBPS) operating units.

### `lending-digital` — Digital Lending / Fintech Lending
NBFC-led BNPL, instant personal loan, gold, salary advance, BNPL, P2P, co-lending.

**India context.** RBI Digital Lending Guidelines (Sep 2022, FLDG circular Jun 2023), NBFC scale-based regulation (NBFC-BL/ML/UL/TL), CKYC + V-CKYC, Account Aggregator data fetch (Sahamati), CIBIL/CRIF/Equifax/Experian bureau pull, repayment-mode prefs (eNACH/UPI-AutoPay/SI), digital sanction letter, KFS (Key Fact Statement) mandate.

### `microfinance` — Microfinance / Inclusive Finance
JLG (joint-liability group), SHG (self-help group), PSL/PSL-Plus, last-mile collection.

**India context.** RBI's microfinance regulations (Mar 2022), MFIN/SaDhan SRO, FI-Index, SHG Bank Linkage, Stree Nidhi.

### `account-aggregator` — Account Aggregator (cross-cut)
AA framework consent flows, FIP/FIU integration, financial-data fetch.

**India context.** Sahamati network, Setu/Finvu/CAMSFinServ/OneMoney/Anumati AA TSPs, RBI NBFC-AA license, ReBIT data standards, consent artefact spec.

---

## Healthcare & Life Sciences

### `provider-hospital` — Provider / Hospital
Multi-specialty hospital, single-specialty, day-care, OPD, IPD, emergency.

**India context.** ABDM HFR enrollment, NABH accreditation reporting, CGHS/ECHS empanelment, Ayushman Bharat PMJAY claim pre-auth, state-scheme cards (Mahatma Phule/Aarogyasri), clinical-establishment-act registration.

### `provider-clinic` — Clinics, Diagnostics, Labs, Pharmacies
OPD-only clinic, diagnostic chain, online pharmacy, telemedicine.

**India context.** Telemedicine Practice Guidelines 2020 (MoHFW + NMC), CDSCO drug-dispensing online pharmacy framework, NABL accredited labs, state pharmacy-council registrations.

### `payer` — Health Insurance Payer
TPA, payer-side claim adjudication.

**India context.** NHCX (National Health Claims Exchange), insurer onboarding, Bima Sugam phase-2 health module.

### `medtech-devices` — Medical Devices / MedTech
Device sales, post-market surveillance, field-service, clinical-engineering.

**India context.** CDSCO Medical Devices Rules 2017 + 2020 amendments, MD-9/MD-10 manufacture/import, MvPI (Materiovigilance), in-vitro diagnostics regulation.

### `pharma-rx` — Pharma — Prescription / Innovator
Branded Rx, MR (medical rep) execution, KOL engagement, hospital tender.

**India context.** UCPMP (Uniform Code for Pharmaceutical Marketing Practices), DPCO price control, NPPA price-cap notifications, Schedule H/H1/X distribution rules, e-Sushrut hospital interop.

### `pharma-generics` — Pharma — Generics / OTC
Generic-Rx, OTC, FMCG-pharma overlap, distributor execution, retail-pharmacy beat plan.

**India context.** Jan Aushadhi (PMBJP) supply, AIOCD-led trade dynamics, retail-chemist primary/secondary sales, Schedule M GMP, e-way bill on stockist transfer.

### `pharma-biotech` — Biotech / Biosimilars
R&D pipeline, clinical-trial mgmt, biosimilar approval.

**India context.** CDSCO Biologic licensing, DBT/RCGM oversight, Schedule Y compliance.

### `clinical-trials` — Clinical Trial Mgmt
Site mgmt, subject recruitment, patient services, eCOA/ePRO, trial-closeout.

**India context.** CDSCO SUGAM portal CT registration, CT Registry of India (CTRI), GCP-India guidelines, ICMR Bioethics, Schedule Y Phase I-IV.

---

## Communications, Media, Energy (CME)

### `telco-consumer` — Telco — Consumer (B2C)
Prepaid, postpaid, FTTH/Broadband, OTT bundling, family plans.

**India context.** TRAI consumer-protection regs, MNP (Mobile Number Portability), DoT licensing, Aadhaar-based eKYC for SIM (post-DoT amendments), Bharat Net last-mile, regional-language USSD/IVR, jio/airtel/vi-tier offer differentiation.

### `telco-enterprise` — Telco — Enterprise (B2B)
Leased lines, MPLS, SD-WAN, SIP-trunk, IoT-SIM, satellite-backhaul.

**India context.** OSP (Other Service Provider) registration, UL-VNO licensing, CUG plans, Bharat Net B2B circuits, GSI cloud-connect.

### `telco-network-ops` — Telco — Network Operations
NOC, fault, fulfillment, inventory.

**India context.** AGR (Adjusted Gross Revenue) accounting traceability, EMF radiation reporting per DoT.

### `media-broadcast` — Broadcast / Cable / DTH
Channel sales, distributor, BARC ratings, ad sales, MSO.

**India context.** TRAI's New Tariff Order (NTO 3.0), MIB self-regulation tiers, BARC India sample, Cable TV (Network Regulation) Act, broadcast-CAS audit.

### `media-digital` — OTT / Digital Media / Publisher
SVOD, AVOD, news publisher, CMS, content-licensing.

**India context.** MIB IT Rules 2021 grievance officer, age-rating self-classification, BharatNet OTT throttling debate, NSE-listed media-house specifics.

### `energy-utilities-power` — Power Discom/Genco/Transco
Distribution, generation, transmission.

**India context.** DISCOM tariff filings (CERC/SERC), Smart Meter National Programme rollout, UDAY-scheme reporting, RPO (Renewable Purchase Obligation), open-access consumers, PFC/REC funding hooks.

### `energy-utilities-water-gas` — Water / Gas Utilities
City gas distribution, water supply, sewerage, smart-water-meter.

**India context.** CGD (City Gas Distribution) rounds (PNGRB), GAIL pipeline tariff, Jal Jeevan Mission (JJM) household-tap reporting, AMRUT-2 city water portfolios.

### `energy-renewables` — Solar / Wind / Hydrogen / Storage
EPC, asset, O&M, IPP, captive, rooftop, FAME-II.

**India context.** PM Surya Ghar Muft Bijli Yojana (rooftop solar subsidy), KUSUM (solar pumps), MNRE's PM-KUSUM portal, PLI for advanced cell, Green Hydrogen Mission, RE bid (SECI/NTPC) lifecycle.

### `oil-and-gas` — Oil, Gas, Downstream
Refining, retail-fuel, lubricant, LPG, CGD, exploration.

**India context.** PPAC daily fuel-pricing dashboards, Ujjwala LPG distribution, Indianoil/HPCL/BPCL retailer ecosystem, ATF aviation distribution, biofuel-blending mandate (E20).

---

## Manufacturing, Auto, Industrial

### `manufacturing-discrete` — Discrete Manufacturing
Auto-components, electronics, capital goods, contract mfg, EMS.

**India context.** PLI scheme (electronics, auto components, telecom, semiconductors), Make-in-India, ZED-cert MSME, ESDM cluster.

### `manufacturing-process` — Process Manufacturing
Chemicals, paints, cement, steel, fertilizers, paper.

**India context.** CPCB consents, hazardous-waste rules, BIS standards, BIS Hallmark for jewelry, FCI/PDS interop for fertilizers.

### `automotive-oem` — Auto OEM (4W / 2W / CV / 3W)
Lead-to-delivery, retail, dealer mgmt, after-sales.

**India context.** Dealer DMS interop (Excelon/Autoline/IDeMS), VAHAN/SARATHI for RC, BS-VI compliance metadata, FAME-II EV-incentive eligibility, Vehicle Scrappage Policy 2022.

### `automotive-aftermarket` — Auto Aftermarket / Service
Multi-brand workshop, service network, parts distribution, FASTag-tied service.

### `automotive-mobility` — Mobility / Fleet / EV
Ride-hail, fleet leasing, EV charging network (CPO/EMSP), battery-swap.

**India context.** OCPI (Open Charge Point Interface) is global; in India tracked under MoP's draft EVCS guidelines; Bharat AC/DC charger spec; FAME-II demand-incentive.

### `industrial-machinery` — Industrial Machinery / Heavy Engineering
Capital goods, project-mode supply, after-sales service-contract.

---

## Consumer & Retail

### `cpg-fmcg` — FMCG / CPG
Food, beverage, personal care, home care, OTC.

**India context.** General Trade (Kirana 12M+ outlets) vs Modern Trade (HoReCa, MT chains, e-com), wholesaler-distributor-retailer hierarchies, GST e-way bill on secondary, FSSAI labeling, BIS, regional-language SKU labeling.

### `cpg-durables` — Consumer Durables
White goods, brown goods, kitchen appliances, smart-home.

**India context.** BEE star-rating compliance, BIS/CRS for electronics, e-waste rules.

### `retail-fashion` — Apparel / Fashion / Lifestyle
EBO, MBO, omnichannel, fast-fashion, LFR.

**India context.** Phygital retail with COD, store-pickup, ONDC apparel-catalog publication, GST 5%/12% slab logic, festive-collection drops.

### `retail-grocery` — Grocery / QSR / Food Service
Hyperlocal grocery, dark store, QSR, cloud kitchen.

**India context.** Hyperlocal 10-min commerce (Blinkit/Zepto/Instamart) ops patterns, FSSAI license, ONDC grocery catalog.

### `retail-pharmacy-omni` — Omnichannel Pharmacy
Online + offline pharmacy, OPD-rx fulfillment.

**India context.** Schedule H/H1/X dispensing online safeguards, e-prescription validation, Telemedicine Practice Guidelines.

### `qsr-foodservice` — QSR / Food Service / Restaurants
Multi-brand QSR, dine-in, delivery aggregator interop.

**India context.** GST 5% restaurant slab (no ITC), aggregator-collected GST (Swiggy/Zomato), FSSAI menu-display rule, regional-cuisine localization.

### `travel-hospitality` — Travel / Hospitality / Hotels
OTA, hotel chain, airline ancillary, cruise, tour-operator.

**India context.** GSTIN on B2B corporate booking, eVisa flows, Incredible India campaign tie-ins, regional airline (Akasa/IndiGo/AirIndia) ecosystem, IRCTC rail-bundle.

### `loyalty-cobrand` — Loyalty / Co-brand
Co-brand credit cards, FMCG loyalty, fuel loyalty, airline FFP.

**India context.** RBI rules on loyalty-as-financial-incentive, GST treatment of points.

### `e-commerce-marketplace` — E-commerce Marketplace
Multi-seller marketplace, ONDC participation.

**India context.** ONDC Buyer-App / Seller-App / Logistics-Provider participation, FDI Press Note 2 marketplace-vs-inventory rules, marketplace fairness rules under DPIIT, GST tax-collection-at-source (TCS) by ECO.

---

## Public Sector & Education

### `government-central` — Central Government
Ministry, DPIIT, MEITY, MoF, MoCI, MoHUA programs.

**India context.** Digital India infra, Aadhaar (UIDAI), DigiLocker, eSign, Umang super-app, NIC infra co-existence, GeM procurement, CCTNS for MHA.

### `government-state` — State Governments
State e-District, CM-helpline, state schemes.

**India context.** State e-District portals (TN, AP, KA, MH, GJ, UP, etc.), CM-Dashboards (CMRDH/Aapke Dwar Sarkar), state-wise IT rules variance, regional-language UI default.

### `government-municipal` — Municipal / ULB
Property-tax, trade-license, water-charge, birth-death certificate, building-plan approval.

**India context.** AMRUT/Smart Cities Mission portals, ULB-tier financial hierarchy, Ease-of-Living index reporting.

### `government-defense` — Defense / Paramilitary
Logistics, recruitment, R&D coordination (DRDO/HAL/BEL).

**India context.** Defense Acquisition Procedure (DAP-2020), Make-I/II/III, iDEX-DIO startup challenge, restricted-cloud requirement (sometimes mandates on-prem).

### `education-k12` — K-12 / School
Admission, attendance, fee, exam, parent-engagement.

**India context.** RTE Section 25 PTR, NEP 2020 5+3+3+4 structure, CBSE/ICSE/state-board affiliations, PARAKH National Assessment.

### `education-higher` — Higher Education / University
Admission, course, exam, alumni, research, hostel.

**India context.** UGC/AICTE compliance, NEP 2020 multidisciplinary HEI, Academic Bank of Credits (ABC), DigiLocker degree, Samarth ERP coexistence, NIRF ranking.

### `education-edtech` — EdTech
B2C upskilling, K12 supplementary, test-prep, vernacular.

**India context.** TPF (Test Prep Federation) self-reg, PMVidyaLakshmi for ed-loans, Swayam OER, Diksha for K12.

### `nonprofit-india` — Nonprofit / NGO / CSR
Foundation, Section 8 company, society, trust, CSR partnership.

**India context.** FCRA (Foreign Contribution Regulation Act) compliance, 12A/80G receipts, CSR Section 135 + Form CSR-1/CSR-2 reporting, SBI FCRA-account, NGO-Darpan listing.

---

## Cross-cutting domains (orthogonal to industry)

These dimensions can co-occur with any industry above.

### `kyc-aml` — KYC / AML / Onboarding
Customer identification, sanction screening, ongoing monitoring.

**India context.** PMLA Rules, V-CKYC video-call, CKYCR upload/download, FATF observations, FIU-IND STR/CTR filing, ENBD-tier sanction list overlay.

### `compliance-data-privacy` — Data Privacy / Residency
Consent, purpose-limitation, retention, RTBF.

**India context.** DPDP Act 2023 (Aug 2023 + draft Rules 2025), data-fiduciary obligations, child-data restrictions, Significant Data Fiduciary tier, RBI sectoral data-localization (payment data on Indian soil), MeitY data-localization pulses, sectoral residency under SEBI/IRDAI/RBI vs DPDP umbrella.

### `tax-gst-india` — Indian Taxation / GST
GST registration, return (GSTR-1/2A/2B/3B/9/9C), e-invoice, e-way bill, TDS/TCS, IT-rule withholding.

**India context.** IRP (Invoice Registration Portal), FY-2024 e-invoice ≥INR 5cr threshold, GSTN APIs, EWB-1/2/3, ITC-04 job-work, anti-profiteering reporting.

### `field-execution` — Field Execution
Sales rep, service tech, surveyor, claim-investigator, MR, FOS (feet-on-street).

**India context.** Bharat 2/3 connectivity-resilient mobile, Hindi/regional UI, two-wheeler vs four-wheeler resource, hyperlocal SLA.

### `contact-center` — Contact Center / CX Ops
Voice, chat, WhatsApp, SMS, IVR, social.

**India context.** TRAI DLT (Distributed Ledger Technology) registration of templates, sender-ID whitelisting, WhatsApp Business API + BSP (Gupshup, Wati, Karix, AiSensy), Indian-context IVR (Hindi + regional menus), recording-storage residency.

### `digital-onboarding` — Digital Onboarding
Self-serve form, doc-upload, e-Sign, video-KYC.

**India context.** Aadhaar e-KYC (UIDAI), DigiLocker pull, e-Sign (NSDL/eMudhra/CDSL), V-CKYC video, NSDL-PAN verification.

### `revenue-billing` — Revenue / Billing / Subscription
Subscription, usage, dunning, revenue recognition.

**India context.** GST e-invoicing on each invoice, INR rounding, partial-period proration, festive-discount accounting.

### `field-service-india` — India-tier Field Service
Connectivity-resilient, regional-language, two-wheeler-fleet.

### `sustainability-esg` — ESG / Sustainability
Scope 1/2/3, BRSR, supplier sustainability.

**India context.** SEBI BRSR Core (top-1000 listed mandatory), PAT scheme, NDC alignment, Carbon Credit Trading Scheme (CCTS), Green-Bond reporting under SEBI.

### `partner-distributor` — Partner / Distributor / Dealer
Dealer hierarchy, distributor onboarding, channel-rebate.

**India context.** Multi-tier distributor (CFA → Super Stockist → Distributor → Wholesaler → Retailer), state-wise CFA structure for FMCG, mandatory Form 49A PAN per partner, GSTIN-per-distinct-state-of-operation.

---

## Selecting industry domains at `/init`

`/init` will ask the user (via `AskUserQuestion`) which industry domains the project serves. The user picks one or more keys from the list above. The chosen keys are written to `.adlc/config.yml` under `industry_domains:` and into `.adlc/context/industry-domains.md` as a header annotation showing "selected domains".

Subsequent skills and reviewer agents read `industry_domains:` to:
- Branch on industry-specific patterns (e.g., RBI digital-lending checks fire only when `lending-digital` or `banking-retail` is selected).
- Route REQ retrieval to lessons tagged with the same industry.
- Surface India-specific anchors (DPDP, GST, ABDM, ONDC, etc.) when applicable.

If a REQ touches an industry not in the project's `industry_domains:` list, `/spec` should warn the user and require either (a) adding the industry to the project config or (b) explicitly tagging the REQ as a one-off cross-domain feature.
