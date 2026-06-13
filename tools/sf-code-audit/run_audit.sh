#!/bin/bash

# Salesforce Audit Tool - Quick Run Script
# Usage: ./run_audit.sh [org-alias] [output-directory]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL_VERSION=$(SCRIPT_DIR="$SCRIPT_DIR" python3 - <<'PY'
import json
import os

script_dir = os.environ["SCRIPT_DIR"]
version_path = os.path.join(script_dir, "tool_version.json")
version = "1.2.11"

if os.path.exists(version_path):
    try:
        with open(version_path, "r", encoding="utf-8") as handle:
            version = str(json.load(handle).get("version", version))
    except Exception:
        pass

print(version)
PY
)

clear

cat << 'EOF'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🚀 SALESFORCE AUDIT TOOL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EOF

echo "Version: v$TOOL_VERSION"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed."
    echo "   Install from: https://www.python.org/downloads/"
    exit 1
fi

# Check if sfdx is installed
if ! command -v sfdx &> /dev/null; then
    echo "❌ Error: Salesforce CLI (sfdx) is not installed."
    echo "   Install from: https://developer.salesforce.com/tools/sfdxcli"
    exit 1
fi

# Get org alias (from argument or prompt)
if [ -z "$1" ]; then
    echo "📋 Available Salesforce Orgs:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    sfdx org list --json | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    orgs = data.get('result', {}).get('nonScratchOrgs', [])
    if not orgs:
        print('  No orgs found. Please authenticate first.')
        sys.exit(1)
    for i, org in enumerate(orgs, 1):
        alias = org.get('alias', 'N/A')
        username = org.get('username', 'N/A')
        status = org.get('connectedStatus', 'Unknown')
        print(f'  {i}. {alias:20} ({username}) - {status}')
except:
    print('  Error listing orgs')
"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    read -p "🔑 Enter org alias (or press Enter to authenticate new org): " ORG_ALIAS
    
    if [ -z "$ORG_ALIAS" ]; then
        echo ""
        echo "🔐 Choose org type:"
        echo "  1. Production"
        echo "  2. Sandbox"
        read -p "Enter choice (1 or 2): " ORG_TYPE
        
        read -p "Enter org alias name: " ORG_ALIAS
        
        if [ "$ORG_TYPE" = "2" ]; then
            echo ""
            echo "🌐 Opening browser for Sandbox authentication..."
            sfdx auth:web:login -a "$ORG_ALIAS" -r https://test.salesforce.com
        else
            echo ""
            echo "🌐 Opening browser for Production authentication..."
            sfdx auth:web:login -a "$ORG_ALIAS"
        fi
        
        if [ $? -ne 0 ]; then
            echo ""
            echo "❌ Authentication failed. Please try again."
            exit 1
        fi
        
        echo ""
        echo "✅ Authentication successful!"
        echo ""
    fi
else
    ORG_ALIAS="$1"
fi

# Get output directory (from argument or use default)
if [ -z "$2" ]; then
    OUTPUT_DIR="./audit-results"
else
    OUTPUT_DIR="$2"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  📊 RUNNING AUDIT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Org:            $ORG_ALIAS"
echo "  Output:         $OUTPUT_DIR"
echo "  Started:        $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Run the audit
python3 "$SCRIPT_DIR/salesforce_audit.py" --sfdx "$ORG_ALIAS" --output-dir "$OUTPUT_DIR"

if [ $? -eq 0 ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ✅ AUDIT COMPLETE!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  📊 Reports generated in: $OUTPUT_DIR"
    echo ""
    
    # Find and list the generated files
    EXCEL_FILE=$(find "$OUTPUT_DIR" -name "SF_Audit_*.xlsx" -type f | head -1)
    MD_FILE=$(find "$OUTPUT_DIR" -name "SF_Audit_*_Summary.md" -type f | head -1)
    
    if [ -n "$EXCEL_FILE" ]; then
        echo "  📄 Excel Report:    $(basename "$EXCEL_FILE")"
    fi
    
    if [ -n "$MD_FILE" ]; then
        echo "  📄 Markdown Summary: $(basename "$MD_FILE")"
    fi
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # Ask if user wants to open the Excel report
    if [ -n "$EXCEL_FILE" ]; then
        read -p "📊 Open Excel report now? (y/n): " OPEN_REPORT
        if [[ "$OPEN_REPORT" =~ ^[Yy]$ ]]; then
            echo ""
            echo "📂 Opening Excel report..."
            
            # Open based on OS
            if [[ "$OSTYPE" == "darwin"* ]]; then
                open "$EXCEL_FILE"
            elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
                xdg-open "$EXCEL_FILE" 2>/dev/null || echo "Please open manually: $EXCEL_FILE"
            elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
                start "$EXCEL_FILE"
            else
                echo "Please open manually: $EXCEL_FILE"
            fi
        fi
    fi
    
    echo ""
    echo "✅ Done! Thank you for using Salesforce Audit Tool."
    echo ""
else
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ❌ AUDIT FAILED"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  Please check the error messages above."
    echo "  See README.md for troubleshooting help."
    echo ""
    exit 1
fi








