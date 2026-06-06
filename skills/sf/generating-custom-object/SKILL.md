---
name: generating-custom-object
description: "Use this skill ONLY to generate the Custom Object metadata file (`.object-meta.xml`) — label, sharing model, nameField, deployment status, search/report/activity flags. Trigger when users say \"create a custom object\", \"generate object metadata\", \"set up an object for...\", or are troubleshooting object deployment errors around sharing models and Master-Detail relationships. Do NOT use this skill for custom fields, validation rules, list views, tabs, page layouts, action overrides, permission sets, or any other artifact that lives in its own metadata file — those have dedicated skills (see Out of Scope below)."
metadata:
  version: "1.1"
---

## When to Use This Skill

Use this skill when you need to:
- Create a new custom object's `.object-meta.xml` file
- Configure object sharing model, name field, and built-in feature flags (search/reports/activities/history)
- Troubleshoot deployment errors specifically about the object metadata file itself (sharing model vs Master-Detail, reserved API names, missing `<deploymentStatus>`, stray `<fullName>` at root)

## Out of Scope — Use a Different Skill

This skill creates the **object only**. Every related artifact below ships in its own metadata file (SFDX source format) and has its own skill or its own REQ. Do not bundle these into a "create object" task — they each warrant a separate REQ if they aren't already in scope, or they can be added later via Setup.

| Artifact | Skill |
|---|---|
| Custom Fields (`.field-meta.xml`) | `generating-custom-field` |
| Validation Rules (`.validationRule-meta.xml`) | `generating-validation-rule` |
| List Views (`.listView-meta.xml`) | `generating-list-view` |
| Custom Tabs (`.tab-meta.xml`) | `generating-custom-tab` |
| FlexiPages / Page Layouts | `generating-flexipage` |
| Permission Sets | `generating-permission-set` |
| Action overrides, compact layouts, search layouts, record types | Out of scope for the ADLC toolkit — configure in Setup, or file a follow-up REQ if metadata-as-code is required |

If the requirement asks for "create a Vehicle object with a tab, a page layout, and an admin permission set", that's three or four REQs (or one REQ with explicit scope across multiple skills) — not a single object generation. Surface this back to the user / `/architect` rather than silently expanding scope.

## Specification

## 1. Overview and Purpose

This document defines the mandatory constraints for generating CustomObject metadata XML (`.object-meta.xml` file). The agent must verify these constraints before outputting XML to prevent Metadata API deployment errors.

**File extension:** `.object-meta.xml`

---

## 2. Syntactic Essentials (Tier 1)

The following constraints must be true for the XML body to deploy successfully.

**Note:** The API Name (fullName) is NOT a tag; it is the filename (e.g., `Vehicle__c.object-meta.xml`).

### Required Elements

| Element | Requirement | Notes |
|---------|-------------|-------|
| `<label>` | Required | Singular UI name |
| `<pluralLabel>` | Required | Plural UI name |
| `<sharingModel>` | Required | See Sharing Model Rules below |
| `<deploymentStatus>` | Required | Always set to `Deployed` |
| `<nameField>` | Required | Primary record identifier (requires `<label>` and `<type>`) |
| `<visibility>` | Required | Always set to `Public` |

### Sharing Model Rules

**Default:** Set `<sharingModel>` to `ReadWrite`.

**Exception:** If this object contains a Master-Detail relationship field, `<sharingModel>` MUST be `ControlledByParent`.

**Decision Logic:**
- IF object has NO Master-Detail field → use `ReadWrite`
- IF object has Master-Detail field → use `ControlledByParent`
- IF a Master-Detail field is being added to an existing child object → that existing object's `<sharingModel>` must also be updated to `ControlledByParent`

**❌ INCORRECT** — Will cause error: `Cannot set sharingModel to ReadWrite on a CustomObject with a MasterDetail relationship field`
```xml
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
  <label>Order Line Item</label>
  <pluralLabel>Order Line Items</pluralLabel>
  <sharingModel>ReadWrite</sharingModel>  <!-- WRONG: Object has a M-D field -->
  <deploymentStatus>Deployed</deploymentStatus>
</CustomObject>
```

**✅ CORRECT:**
```xml
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
  <label>Order Line Item</label>
  <pluralLabel>Order Line Items</pluralLabel>
  <sharingModel>ControlledByParent</sharingModel>  <!-- CORRECT -->
  <deploymentStatus>Deployed</deploymentStatus>
</CustomObject>
```

---

## 3. Smart Defaults & Decision Logic (Tier 2)

The agent must choose which features to enable based on the object's intended use case.

### A. The Name Field Decision

| Type | When to Use | Additional Requirements |
|------|-------------|------------------------|
| **Text** | Default for human-named entities (Projects, Locations, Teams) | None |
| **AutoNumber** | Use for transactions, logs, or IDs (Invoices, Requests, Tickets) | Must include `<displayFormat>` (e.g., `INV-{0000}`) and `<startingNumber>1</startingNumber>` |

**Text Name Field Example:**
```xml
<nameField>
  <label>Project Name</label>
  <type>Text</type>
</nameField>
```

**AutoNumber Name Field Example:**
```xml
<nameField>
  <label>Invoice Number</label>
  <type>AutoNumber</type>
  <displayFormat>INV-{0000}</displayFormat>
  <startingNumber>1</startingNumber>
</nameField>
```

### B. Object Description

**`<description>`**: Mandatory. Every object must contain a professional summary.

If the intent is vague, generate a summary:
> "Object used to track and manage [Intent] within the organization."
### C. Junction Object Naming

If the object is a many-to-many link between two parents, name the object by combining the two parent entities to ensure the schema remains intuitive.

**Examples:**
- `Position_Candidate__c` (links Position and Candidate)
- `Job_Application__c` (links Job and Application)

### D. Feature Enablement (Clean XML)

To maintain "Clean XML," only include optional tags when deviating from the Salesforce platform default of `false`.

**Scenario A: User-Facing Objects (Apps, Trackers, Business Entities)**
- Trigger: The object is intended for direct user interaction
- Action: Set `<enableSearch>`, `<enableReports>`, `<enableActivities>`, and `<enableHistory>` to `true`

**Scenario B: System-Facing Objects (Junctions, Background Logs)**
- Trigger: The object exists for technical associations or background data
- Action: Omit these tags to keep the UI clean and the XML lean

---

## 4. Critical Constraints & Common Failures

### Reserved Words

Never use reserved words as API names for Custom Objects or Custom Fields:

| Category | Reserved Words (Do Not Use as API Names) |
|----------|------------------------------------------|
| SOQL/SQL | `Select`, `From`, `Where`, `Limit`, `Order`, `Group` |
| System | `User`, `External`, `View`, `Type` |
| Temporal | `Date`, `Number` |

### Relationship Cap

Do not create more than **2 Master-Detail relationships** for a single object. If a third relationship is required, use a Lookup instead.

### XML Root Element

Do NOT include the `<fullName>` tag at the root of the `.object-meta.xml` file. The API name is derived from the filename.

**❌ INCORRECT:**
```xml
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
  <fullName>Vehicle__c</fullName>  <!-- WRONG: Remove this -->
  <label>Vehicle</label>
</CustomObject>
```

**✅ CORRECT:**
```xml
<CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">
  <label>Vehicle</label>
  <!-- fullName comes from filename: Vehicle__c.object-meta.xml -->
</CustomObject>
```

### Naming Pattern Reference

| Metadata Type | Naming Pattern | Example |
|---------------|----------------|---------|
| Custom Objects | Ends with `__c` | `Vehicle__c` |
| Custom Fields  | Ends with `__c` | `Start_Date__c` |

(Validation rules, list views, tabs, etc. follow their own naming conventions — see their dedicated skills.)

---

## 5. Verification Checklist

Before generating the Custom Object XML, verify:

### Syntactic Checks
- [ ] Are both `<label>` and `<pluralLabel>` present?
- [ ] Is `<deploymentStatus>` set to `Deployed`?
- [ ] Is `<visibility>` set to `Public`?
- [ ] Does `<nameField>` include both `<label>` and `<type>`?
- [ ] If `<type>` is `AutoNumber`, are `<displayFormat>` and `<startingNumber>` included?

### Sharing Model Check (Critical)
- [ ] Does this object have a Master-Detail relationship field?
    - If YES → `<sharingModel>` MUST be `ControlledByParent`
    - If NO → `<sharingModel>` should be `ReadWrite`

### Constraint Checks
- [ ] Is the API name free of reserved words?
- [ ] Are there 2 or fewer Master-Detail relationships?
- [ ] Is `<fullName>` absent from the XML root?

### Architectural Checks
- [ ] Is `<description>` present with a meaningful summary?
- [ ] Are `<enableSearch>` and `<enableReports>` set to `true` if user-facing?
- [ ] Does the filename match the intended API name?

### Scope Check
- [ ] Did this skill produce ONLY the `.object-meta.xml` file (no inline fields, validation rules, list views, tabs, layouts, action overrides)? Anything else belongs in its own file generated by its own skill, or a separate REQ.
