---
name: generating-permission-set
description: "Generates correct, deployable Salesforce permission set metadata (PermissionSet XML) with object, field, user, and app permissions. Use this skill when creating or editing permission set metadata, object permissions, field-level security (FLS), tab visibility, or deploying permission sets."
compatibility: Salesforce Metadata API v60.0+
metadata:
  author: sf-skills
  version: "1.0"
---

## When to Use This Skill

Use when generating or editing permission set metadata, or when granting object, field, user, and app permissions.

## Step 1: Define Core Properties

Start by defining the required permission set properties:

```xml
<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>YourPermissionSetName</fullName>
    <label>Display Name for Administrators</label>
    <description>Clear description of purpose and intended audience</description>
</PermissionSet>
```

**Naming conventions:**
- Use descriptive API names (e.g., `Sales_Manager_Access`)

## Step 2: Configure Object Permissions

Add CRUD permissions for standard and custom objects:

```xml
<objectPermissions>
    <allowCreate>true</allowCreate>
    <allowRead>true</allowRead>
    <allowEdit>true</allowEdit>
    <allowDelete>false</allowDelete>
    <modifyAllRecords>false</modifyAllRecords>
    <viewAllRecords>false</viewAllRecords>
    <viewAllFields>false</viewAllFields>
    <object>Account</object>
</objectPermissions>
```

## Step 3: Set Field-Level Security

Define field permissions ONLY for fields that are eligible for FLS — not every field on an object qualifies. Mixing in required fields, system fields, master-detail relationships, or audit-only fields is the #1 cause of permission-set deploy failures and the bug that bit AGN-REQ-003 in the AGN_KYC project.

```xml
<fieldPermissions>
    <editable>true</editable>
    <readable>true</readable>
    <field>Account.SSN__c</field>
</fieldPermissions>
```

### What MUST NOT appear in `<fieldPermissions>` — exclusion gate

Treat the categories below as a hard "do not list" gate. The pre-flight script (Step 7 below) enforces them, but the gate exists so authoring stops here, not at deploy time.

| Category | Examples | Why excluded |
|---|---|---|
| **System / audit-managed fields** | `Id`, `CreatedById`, `CreatedDate`, `LastModifiedById`, `LastModifiedDate`, `SystemModstamp`, `IsDeleted`, `OwnerId`, `LastActivityDate`, `LastViewedDate`, `LastReferencedDate`, `RecordTypeId`, `MayEdit`, `IsLocked` | Platform-managed, not user-settable. Listing them yields "field is not eligible for field-level security" deploy errors. The platform always grants the right access automatically. |
| **Required fields** | Any field with `<required>true</required>` in its `.field-meta.xml`; standard required fields like `Account.Name`, `Contact.LastName`, `Task.Subject`; master-detail parent lookups | The platform always grants access to required fields. Adding `<fieldPermissions>` for them fails deploy with `Cannot grant FLS on a required field`. |
| **Master-detail relationships** | The lookup field on the child side of any M-D | Implicitly required + permission-controlled by the parent. |
| **Auto-number fields** | Often the Name field on transaction objects (Invoices, Tickets) | Platform-generated; `editable=true` always fails. If listed, MUST set `editable=false`. |
| **Formula fields** | Any `<formula>` in `.field-meta.xml`, including roll-up summaries | Read-only by definition; `editable=true` always fails. If listed, MUST set `editable=false`. |
| **Compound fields** | `Account.Address`, `Contact.MailingAddress`, `Person Account.Name` | Composite of other fields; FLS is set on the components, not the compound. |

### What SHOULD appear in `<fieldPermissions>`

- Custom fields (`__c`) that aren't required and aren't formulas
- Standard fields that are user-settable AND not in the exclusion list above (e.g., `Account.Industry`, `Contact.Email`, `Opportunity.StageName`)

### Decision tree before adding a field

1. Is the field name in the system-fields exclusion list above? → SKIP. Don't add it.
2. Open the field's `.field-meta.xml`. Does it contain `<required>true</required>`? → SKIP.
3. Does it contain `<formula>` or `<type>AutoNumber</type>` or `<type>MasterDetail</type>`? → SKIP unless you specifically need read-only with `editable=false`, and even then prefer omitting.
4. Otherwise → add with `<readable>true</readable>` plus `<editable>true</editable>` (or `false` for read-only).

### Reference snippets

A required field — DO NOT include in `<fieldPermissions>`:
```xml
<fields>
    <fullName>FieldName__c</fullName>
    <required>true</required>
</fields>
```

Field reference format inside `<fieldPermissions>`:
- Use `ObjectName.FieldName` (e.g., `Account.Industry`, `Custom__c.Status__c`)
- `editable=true` implies `readable=true`; setting `readable=false` with `editable=true` is invalid
- If granting blanket access, prefer object-level `<viewAllFields>true</viewAllFields>` over enumerating every field

## Step 4: Grant User Permissions

Add system-level permissions for features and capabilities:

```xml
<userPermissions>
    <enabled>true</enabled>
    <name>ApiEnabled</name>
</userPermissions>
<userPermissions>
    <enabled>true</enabled>
    <name>RunReports</name>
</userPermissions>
```

**Common permissions:**
- `ApiEnabled`: API access
- `ViewSetup`: View Setup menu
- `ManageUsers`: User management
- `RunReports`: Report execution

**Security review required for:**
- `ViewAllData`: Read all records
- `ModifyAllData`: Edit all records
- `ManageUsers`: User administration

## Step 5: Configure App and Tab Visibility

Make applications and tabs visible to users:

```xml
<applicationVisibilities>
    <application>Sales_Console</application>
    <visible>true</visible>
</applicationVisibilities>
<tabSettings>
    <tab>CustomTab__c</tab>
    <visibility>Visible</visibility>
</tabSettings>
```

**Application visibility options:**
- <visible> can be true or false

**Tab visibility options:**
- `Visible`: The tab is available on the All Tabs page and appears in the visible tabs for its associated app. Can be customized.
- `Available`: The tab is available on the All Tabs page. Individual users can customize their display to make the tab visible in any app
- `None`: Not visible

**CRITICAL - Tab Naming:**
- Custom object tabs: MUST include the __c suffix (e.g., MyCustomObject__c)
- Standard object tabs: Use the object name with "standard-" prefix (e.g., standard-Account, standard-Contact)
- The tab name matches the object's API name exactly

## Step 6: Add Apex and Visualforce Access (Optional)

Grant access to custom code:

```xml
<classAccesses>
    <apexClass>CustomController</apexClass>
    <enabled>true</enabled>
</classAccesses>
<pageAccesses>
    <apexPage>CustomPage</apexPage>
    <enabled>true</enabled>
</pageAccesses>
```

## Step 7: Set License and Record Type Settings (Optional)

Specify license requirements and record type visibility:

```xml
<license>Salesforce</license>
<hasActivationRequired>false</hasActivationRequired>
<recordTypeVisibilities>
    <recordType>Account.Business</recordType>
    <visible>true</visible>
    <default>true</default>
</recordTypeVisibilities>
```
## Step 8: Set Agent Access (Optional)
                                              
Enable access to Agentforce Employee Agents for users assigned to this permission set:

<agentAccesses>
    <agentName>Sales_Assistant_Agent</agentName>
    <enabled>true</enabled>
</agentAccesses>

Field requirements:
- agentName (Required): The developer name of the employee agent
- enabled (Required): Set to true to grant access, false to deny

Important:
- Agent names must match existing Agentforce Employee Agent developer names

## Validation Checklist

Before deploying, verify:
- [ ] fullName, label, description set
- [ ] Permissions follow least privilege
- [ ] No required fields in `<fieldPermissions>`
- [ ] No duplicate permissions
- [ ] No lengthy comments

## Local pre-flight (REQ-B — always run before deploy)

Run the perm-set FLS pre-flight script. It queries the target org's `FieldDefinition` (Tooling API) once per object and validates every `<fieldPermissions>` entry against the FLS-eligibility rules — this catches the entire class of "field is required / formula / master-detail / auto-number / not in org" failures locally instead of waiting 60-90s for `sf project deploy validate` to surface them.

```sh
sh tools/sf-preflight/check.sh permsets \
  --workspace force-app \
  --target-org "$ALIAS"
```

Add `--offline` to skip the Tooling API call and validate only the XML structure (use during pure authoring; never as the final gate). Add `--json` for machine-readable output.

Exit codes: `0` = clean, `1` = at least one finding (BLOCK), `2` = invocation error.

## What Causes Deployment Failure

- **Field permissions on required fields:** Any required field in `<fieldPermissions>` fails deployment. Required fields cannot have FLS; omit them entirely. The pre-flight script (above) catches this automatically by reading `FieldDefinition.IsNillable` from the org.
- **Field permissions on formula / auto-number / master-detail fields with `editable=true`:** Salesforce rejects these. Pre-flight catches them via `IsCalculated`, `IsAutoNumber`, and `DataType=MasterDetail`.
- **Field doesn't exist in target org:** typos, namespace mismatches, deletion drift. Pre-flight catches by missing `FieldDefinition` row.
- **Incorrect API names:** Using the wrong name or missing suffixes (e.g. missing `__c` for custom objects, fields, tabs) cause failure.

## Deployment

Deploy using Salesforce CLI