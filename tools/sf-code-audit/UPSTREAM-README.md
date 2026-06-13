# Salesforce Code Audit Tool v1.2.11

**Automated Salesforce Org Quality Analysis**

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 📚 Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [What Gets Analyzed](#what-gets-analyzed)
- [Installation](#installation)
- [Authentication](#authentication)
- [Usage](#usage)
- [Reports](#reports)
- [Grading System](#grading-system)
- [Troubleshooting](#troubleshooting)
- [Requirements](#requirements)
- [FAQ](#faq)

---

## 🎯 Overview

This tool performs comprehensive static analysis of Salesforce orgs, evaluating:

- **Test Coverage** - Org-wide and class-level analysis
- **Governor Limit Violations** - SOQL/DML in loops, indirect violations
- **Security Issues** - CRUD/FLS violations, SOQL injection, XSS
- **Performance Problems** - Non-restrictive queries, inefficient patterns
- **Best Practices** - Code quality and maintainability
- **Lightning Web Components** - Security and best practices

**Key Features:**
- ✅ Accurate line numbers (jump directly to issues)
- ✅ Smart multi-line query detection
- ✅ Metadata exclusion (no false positives)
- ✅ 97% reduction in false positives
- ✅ Automated grading (5-tier system)
- ✅ Excel + Markdown reports

---

## 🚀 Quick Start

**3 Simple Steps:**

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Authenticate (browser opens)
sfdx auth:web:login -a myorg

# 3. Run audit
python3 salesforce_audit.py
```

**Done!** Check `./audit_reports/` for your Excel report (5-10 minutes).

For detailed examples, see [START_HERE.md](START_HERE.md).

### Optional: Automatic Update Prompt

If you want users to be prompted when a new zip release is published:

1. Copy `update_config.example.json` to `update_config.json`
2. Set `manifest_url` to a hosted JSON manifest
3. Publish a `latest-release.json` file using `latest-release.example.json` as the template

Once configured, the tool checks for updates at startup, prompts the user to install the latest version, downloads the new zip, installs dependencies, and relaunches the newer version automatically.

---

## 📊 What Gets Analyzed

### **1. Test Coverage**
- Org-wide coverage percentage
- Class-by-class coverage analysis
- Identifies classes below 75% threshold
- Excludes Site/Community auto-generated classes

### **2. Governor Limit Violations**

**SOQL in Loops:**
- Direct SOQL queries inside loops
- Indirect SOQL through helper methods
- Accurate line numbers for violations

**DML in Loops:**
- Direct DML operations inside loops
- Indirect DML through helper methods
- Insert, Update, Delete, Upsert operations

**Non-Restrictive Queries:**
- SELECT queries without WHERE clause
- Queries on large data objects
- Excludes metadata objects and custom settings
- Multi-line query support

### **3. Security Vulnerabilities**

- CRUD/FLS violations
- SOQL injection risks
- XSS (Cross-Site Scripting) vulnerabilities
- Insecure endpoints
- Hardcoded credentials

### **4. Performance Issues**

- Queries without proper filters
- Inefficient patterns
- Expensive operations in loops
- Future method overuse

### **5. Best Practices**

- Code quality patterns
- Maintainability issues
- Design pattern compliance
- Naming conventions

### **6. Lightning Web Components**

- XSS vulnerabilities
- Unsafe HTML usage
- Security best practices
- API version compliance

### **7. Data Model**

- Custom objects analysis
- Field count per object
- Relationship mapping
- Formula field usage

---

## 💿 Installation

### **Prerequisites:**

- **Python 3.8+** (check: `python3 --version`)
- **Salesforce CLI** (SFDX) - [Install Guide](https://developer.salesforce.com/tools/sfdxcli)
- **Salesforce Org Access** (API Enabled + View All Data)
- **Internet Connection**

### **Install Salesforce CLI:**

```bash
# macOS
brew install sfdx-cli

# Windows
# Download from: https://developer.salesforce.com/tools/sfdxcli

# Linux
npm install -g sfdx-cli
```

### **Install Python Dependencies:**

```bash
pip install -r requirements.txt
```

### **Optional: Configure Automatic Updates**

Create `update_config.json` in the tool folder:

```json
{
  "enabled": true,
  "manifest_url": "https://your-company-hosting.example.com/salesforce-audit-tool/latest-release.json",
  "prompt_for_install": true,
  "auto_install": false,
  "copy_local_config": true,
  "verify_sha256": true
}
```

Host a manifest JSON that looks like:

```json
{
  "latest_version": "1.2.11",
  "download_url": "https://your-company-hosting.example.com/salesforce-audit-tool/salesforce-audit-tool-v1.2.11.zip",
  "sha256": "replace-with-real-zip-sha256",
  "notes_url": "https://your-company-hosting.example.com/salesforce-audit-tool/releases/1.2.11"
}
```

Useful commands:

```bash
python3 salesforce_audit.py --check-updates
python3 salesforce_audit.py --check-updates --yes-update
```

**Dependencies:**
- `simple-salesforce` - Salesforce API client
- `openpyxl` - Excel report generation
- `PyYAML` - Configuration (backward compatibility)
- `tqdm` - Progress bars

---

## 🔐 Authentication

### **Web Browser Authentication (Recommended)**

**Simplest and most secure method:**

```bash
# Authenticate to any org
sfdx auth:web:login -a myorg

# List authenticated orgs
sfdx force:org:list

# Set default org
sfdx config:set defaultusername=myorg

# Remove org
sfdx auth:logout -u myorg
```

**Benefits:**
- ✅ Works with MFA (multi-factor authentication)
- ✅ Secure (credentials stored by Salesforce CLI)
- ✅ No config files needed
- ✅ No security tokens required

### **Multiple Orgs:**

```bash
# Authenticate to multiple orgs
sfdx auth:web:login -a prod
sfdx auth:web:login -a uat
sfdx auth:web:login -a dev

# Run audits on each
python3 salesforce_audit.py --sfdx prod --output-dir ./prod-audit
python3 salesforce_audit.py --sfdx uat --output-dir ./uat-audit
python3 salesforce_audit.py --sfdx dev --output-dir ./dev-audit
```

---

## 💻 Usage

### **Basic Usage:**

```bash
# Auto-detect default org
python3 salesforce_audit.py

# Interactive mode (select org)
python3 salesforce_audit.py -i

# Specific org
python3 salesforce_audit.py --sfdx myorg

# Custom output directory
python3 salesforce_audit.py --output-dir ./my-reports
```

### **Command-Line Options:**

```bash
python3 salesforce_audit.py [OPTIONS]

Options:
  -h, --help              Show help message
  -i, --interactive       Interactive mode (select org)
  --sfdx ORG_ALIAS        Use specific SFDX org
  --output-dir PATH       Custom output directory (default: ./audit_reports)
  --config FILE           Custom config file (optional, backward compatibility)
  --verbose               Enable detailed logging
  --version               Show version information
```

### **Examples:**

```bash
# Example 1: Auto-detect and run
python3 salesforce_audit.py

# Example 2: Interactive mode
python3 salesforce_audit.py -i

# Example 3: Production org with custom output
python3 salesforce_audit.py --sfdx prod --output-dir ./prod-audit-2025-01

# Example 4: Multiple org comparison
python3 salesforce_audit.py --sfdx prod --output-dir ./prod
python3 salesforce_audit.py --sfdx uat --output-dir ./uat
python3 salesforce_audit.py --sfdx dev --output-dir ./dev

# Example 5: Verbose logging for debugging
python3 salesforce_audit.py --sfdx myorg --verbose
```

---

## 📋 Reports

### **Excel Report (6 Sheets):**

#### **1. Overview**
- Org summary and grade
- Coverage metrics
- Issue counts by severity
- Key recommendations

#### **2. Coverage**
- Class-by-class coverage analysis
- Coverage percentage
- Line counts (total, covered, uncovered)
- Classes below threshold

#### **3. Issues**
- All violations with accurate line numbers
- Severity classification (Critical, High, Medium, Low)
- Issue type and description
- Affected classes and methods

#### **4. Data Model**
- Custom objects
- Field counts
- Record counts
- Relationships

#### **5. LWC**
- Lightning Web Components analysis
- Security issues
- Best practices violations
- Component details

#### **6. Grading**
- Detailed scoring breakdown
- Category-wise grades
- Weighted scoring
- Improvement areas

### **Markdown Summary:**

- Executive summary
- Key metrics
- Top issues
- Recommendations
- Org health status

**Report Location:** `./audit_reports/SF_Audit_[OrgName]_[Timestamp].xlsx`

---

## 🎓 Grading System

### **6-Tier Scoring:**

| Grade | Coverage | Critical Issues | Description |
|-------|----------|-----------------|-------------|
| **Excellent** ✨ | ≥ 90% | 0 | Production-ready, 0 High issues, < 15 Medium issues |
| **Very Good** 🌟 | ≥ 85% | 0 | Very good quality, < 10 High issues, < 30 Medium issues |
| **Good** 👍 | ≥ 75% | ≤ 3 | Good quality, may have < 15 High issues |
| **Average** 📊 | 70-75% | ≤ 5 | Meets basic standards, < 50 High issues |
| **Below Average** ⚠️ | 50-70% | ≤ 10 | Significant quality issues, below average risk band |
| **Poor** 🚨 | < 50% | ≥ 10 | Severe defects, imminent production risks, or loops detected |

### **Grading Logic (Waterfall Approach):**

The tool uses a **"lowest grade wins"** waterfall logic, checking from worst to best:

#### **Poor Grade Triggers** (Most Severe)
- ≥ 10 Critical issues
- Org coverage < 50%
- SOQL/DML in loops detected

#### **Below Average Triggers**
- Coverage 50-70%
- Critical issues up to 10
- Used when higher grade bands are not met
- Note: because `Poor` also includes loops and the tool uses waterfall grading, loop violations land in `Poor`

#### **Average Triggers**
- Coverage 70-75%
- ≤ 5 Critical issues
- < 50 High issues

#### **Good Triggers**
- ≥ 75% coverage
- ≤ 3 Critical issues
- < 15 High issues

#### **Very Good Triggers**
- 0 Critical issues
- < 10 High issues
- < 30 Medium issues
- ≥ 85% coverage

#### **Excellent Triggers**
- 0 Critical issues
- 0 High issues
- < 15 Medium issues
- ≥ 90% org coverage

### **Issue Criticality Levels:**

#### **🔴 Critical** (Security & Performance)
- Governor limit violations: `SOQL_IN_LOOP`, `DML_IN_LOOP`, `INDIRECT_SOQL`, `INDIRECT_DML`
- Security: `ApexCRUDViolation`, `ApexSOQLInjection`, `ApexXSSFromEscapeFalse`, `ApexBadCrypto`
- Performance: `AvoidNonRestrictiveQueries`, `OperationWithHighCostInLoop`

#### **🟠 High** (Major Quality Concerns)
- Missing test patterns: `ApexUnitTestClassShouldHaveRunAs`
- Hardcoded IDs: `AvoidHardcodingId`
- Async issues: `FutureMethod`, `AsyncInTrigger`
- Classes with < 90% test coverage

#### **🟡 Medium** (Best Practices)
- Categories: `BestPractices`, `Design`, `ErrorProne`, `DataModel`
- Code quality and maintainability issues

#### **🔵 Low** (Minor Improvements)
- Style issues, naming conventions, minor optimizations

### **Key Grading Rules:**

1. **SOQL/DML in loops = Automatic Poor**
2. **Critical issues are heavily penalized**: 10+ = Poor, 6-10 typically caps at Below Average
3. **Coverage thresholds are strict**:
   - < 50% = Poor
   - 50-70% = Below Average (at best)
   - 70-75% = Average (at best)
   - 75-85% = Good (at best)
   - 85-90% = Very Good (at best)
   - 90%+ = Required for Excellent
4. **High and Medium counts matter**:
   - 15+ High issues prevents Good or better
   - 10+ High issues prevents Very Good
   - 30+ Medium issues prevents Very Good

### **📚 Need More Details?**

For comprehensive grading system documentation with examples and detailed explanations, see:
- **[GRADING_SYSTEM_DETAILED.md](GRADING_SYSTEM_DETAILED.md)** - Complete 6-tier grading guide with examples

---

## 🆘 Troubleshooting

### **Common Issues:**

#### **"No authenticated orgs found"**
```bash
# Solution: Authenticate first
sfdx auth:web:login -a myorg
```

#### **"SFDX CLI not found"**
```bash
# Solution: Install Salesforce CLI
# macOS:
brew install sfdx-cli

# Windows: Download from
# https://developer.salesforce.com/tools/sfdxcli

# Linux:
npm install -g sfdx-cli
```

#### **"Session expired"**
```bash
# Solution: Re-authenticate
sfdx auth:web:login -a myorg
```

#### **"Permission denied" errors**
- **Issue:** User lacks API access or View All Data
- **Solution:** Grant permissions in Salesforce Setup

#### **Slow performance**
- **Issue:** Large org with many classes
- **Solution:** Normal for orgs with 500+ classes (10-15 minutes)

For comprehensive troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## 📋 Requirements

### **Salesforce Permissions:**

- **API Enabled**
- **View All Data** (or equivalent read permissions)
- **View Setup and Configuration**

### **User Profile Requirements:**

The audit tool requires read access to:
- Apex Classes and Triggers
- Lightning Web Components
- Custom Objects and Fields
- Test Results

**Recommended:** System Administrator or API Only user.

### **API Limits:**

The tool uses Salesforce API calls:
- Approximately 100-500 API calls per audit
- Tooling API for metadata retrieval
- Standard API for data queries

Ensure your org has sufficient API calls available.

---

## ❓ FAQ

### **Q: How long does an audit take?**
**A:** 5-10 minutes for typical orgs (500 classes). Larger orgs may take 10-15 minutes.

### **Q: Does it modify my org?**
**A:** No. The tool is read-only and only retrieves metadata.

### **Q: Can I run it on production?**
**A:** Yes. It's safe to run on production (read-only).

### **Q: Does it work with sandboxes?**
**A:** Yes. Works with production, sandboxes, developer orgs, and scratch orgs.

### **Q: Can I automate it in CI/CD?**
**A:** Yes. Use SFDX auth URLs for automated authentication.

### **Q: What about false positives?**
**A:** The tool includes smart detection to minimize false positives:
- Multi-line SOQL queries handled correctly
- Metadata objects excluded
- Custom settings excluded
- 97% reduction vs basic analyzers

### **Q: Can I customize the rules?**
**A:** Yes. Edit detection patterns in `pattern_matcher.py`.

### **Q: Does it support multiple API versions?**
**A:** Yes. Defaults to latest, configurable in the script.

### **Q: Can I export results?**
**A:** Yes. Excel format is easily exportable and shareable.

### **Q: Does it work offline?**
**A:** No. Requires internet connection to access Salesforce APIs.

### **Q: What about managed packages?**
**A:** Managed package code is not accessible via API (Salesforce limitation).

---

## 📖 Additional Documentation

- **[START_HERE.md](START_HERE.md)** - Quick start with examples
- **[GRADING_SYSTEM_DETAILED.md](GRADING_SYSTEM_DETAILED.md)** - Complete 6-tier grading guide with examples
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Comprehensive problem solving
- **[QUICK_REFERENCE.txt](QUICK_REFERENCE.txt)** - Command cheat sheet

---

## 🔄 Version History

**v1.2.11 (April 2026)**
- Added the refreshed PDF executive summary with cleaner formatting, metadata snapshot details, and grading explanation sections
- Bumped release metadata, installer docs, updater manifests, and package version references to `1.2.11`

**v1.2.10 (April 2026)**
- Added same-file helper-method tracing for `Indirect SOQL in Loop` and `Indirect DML in Loop`
- Detects multiline bracket-split SOQL inside loops and `Database.query()` / `Database.queryWithBinds()` / `Database.getQueryLocator()` usage in loops
- Improved multiline query collection so related SOQL rules use the correct query span more consistently
- Added focused regression tests for direct, indirect, dynamic, and multiline loop findings

---

## 🤝 Contributing

Found a bug or have a suggestion? Please contact your Salesforce architect team.

---

## 📝 License

Internal use only. Contact your organization for licensing details.

---

## 🎉 Ready to Start!

```bash
pip install -r requirements.txt
sfdx auth:web:login -a myorg
python3 salesforce_audit.py
```

For more details, check [START_HERE.md](START_HERE.md) →

**Questions?** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) or run `python3 salesforce_audit.py --help`

---

**Happy auditing!** 🚀
