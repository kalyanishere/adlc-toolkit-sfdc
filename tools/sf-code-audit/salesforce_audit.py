#!/usr/bin/env python3
"""
Salesforce Code Audit Tool
Main script that orchestrates the complete audit process
"""

import os
import sys
import yaml
import logging
import argparse
import subprocess
import json
import getpass
import re
import shutil
import hashlib
import tempfile
import zipfile
from datetime import datetime
from typing import Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from tqdm import tqdm

# Import audit modules
from sf_utils import SalesforceConnector, MetadataRetriever, StaticAnalysisRunner
from pattern_matcher import analyze_apex_code, ViolationType
from grading_engine import (
    GradingEngine, IssueCounts, CoverageStats, Criticality
)
from report_generator import ExcelReportGenerator, MarkdownReportGenerator, PDFReportGenerator
from lwc_analyzer import analyze_lwc_component

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOOL_METADATA_PATH = os.path.join(SCRIPT_DIR, 'tool_version.json')
UPDATE_CONFIG_PATH = os.path.join(SCRIPT_DIR, 'update_config.json')
DEFAULT_TOOL_VERSION = '1.2.11'


def _load_tool_version() -> str:
    """Load the tool version from local metadata when available."""
    if os.path.exists(TOOL_METADATA_PATH):
        try:
            with open(TOOL_METADATA_PATH, 'r', encoding='utf-8') as handle:
                metadata = json.load(handle)
            version = str(metadata.get('version', '')).strip()
            if version:
                return version
        except (OSError, ValueError, TypeError):
            pass
    return DEFAULT_TOOL_VERSION


TOOL_VERSION = _load_tool_version()


class SelfUpdater:
    """Checks a remote manifest and can install a newer zip release."""

    def __init__(self, script_dir: str, current_version: str):
        self.script_dir = script_dir
        self.current_version = current_version

    @staticmethod
    def _parse_version(version: str) -> List[int]:
        """Convert dotted version strings into comparable integer lists."""
        parts = re.findall(r'\d+', str(version))
        return [int(part) for part in parts] if parts else [0]

    @classmethod
    def _is_newer_version(cls, candidate: str, current: str) -> bool:
        """Return True when candidate is newer than current."""
        candidate_parts = cls._parse_version(candidate)
        current_parts = cls._parse_version(current)
        max_len = max(len(candidate_parts), len(current_parts))
        candidate_parts.extend([0] * (max_len - len(candidate_parts)))
        current_parts.extend([0] * (max_len - len(current_parts)))
        return candidate_parts > current_parts

    def load_settings(self, manifest_override: Optional[str] = None) -> Dict:
        """Load updater settings from file and environment overrides."""
        settings = {
            'enabled': True,
            'manifest_url': None,
            'prompt_for_install': True,
            'auto_install': False,
            'copy_local_config': True,
            'verify_sha256': True,
        }

        if os.path.exists(UPDATE_CONFIG_PATH):
            try:
                with open(UPDATE_CONFIG_PATH, 'r', encoding='utf-8') as handle:
                    file_settings = json.load(handle)
                if isinstance(file_settings, dict):
                    settings.update(file_settings)
            except (OSError, ValueError, TypeError):
                print("⚠️  Warning: Unable to parse update_config.json. Skipping file-based updater settings.")

        env_manifest = os.environ.get('SF_AUDIT_UPDATE_MANIFEST_URL')
        if env_manifest:
            settings['manifest_url'] = env_manifest

        env_auto_install = os.environ.get('SF_AUDIT_AUTO_INSTALL_UPDATE')
        if env_auto_install is not None:
            settings['auto_install'] = env_auto_install.strip().lower() in {'1', 'true', 'yes', 'y'}

        env_disable = os.environ.get('SF_AUDIT_DISABLE_UPDATES')
        if env_disable is not None:
            settings['enabled'] = env_disable.strip().lower() not in {'1', 'true', 'yes', 'y'}

        if manifest_override:
            settings['manifest_url'] = manifest_override

        return settings

    def fetch_manifest(self, manifest_url: str) -> Dict:
        """Retrieve the latest-release manifest from a URL."""
        request = Request(manifest_url, headers={'User-Agent': f'SalesforceAuditTool/{self.current_version}'})
        with urlopen(request, timeout=20) as response:
            payload = response.read().decode('utf-8')
        manifest = json.loads(payload)
        if not isinstance(manifest, dict):
            raise ValueError("Update manifest must be a JSON object.")
        return manifest

    def _find_existing_install(self, version: str) -> Optional[str]:
        """Locate an already-downloaded sibling install for the target version."""
        install_base = os.path.dirname(self.script_dir)
        for entry in os.scandir(install_base):
            if not entry.is_dir():
                continue
            metadata_path = os.path.join(entry.path, 'tool_version.json')
            audit_script_path = os.path.join(entry.path, 'salesforce_audit.py')
            if not (os.path.exists(metadata_path) and os.path.exists(audit_script_path)):
                continue
            try:
                with open(metadata_path, 'r', encoding='utf-8') as handle:
                    metadata = json.load(handle)
                if str(metadata.get('version', '')).strip() == version:
                    return entry.path
            except (OSError, ValueError, TypeError):
                continue
        return None

    def _copy_local_files(self, target_dir: str, enabled: bool):
        """Carry local updater/app config into the newly installed folder."""
        if not enabled:
            return

        for filename in ('update_config.json', 'config.yaml'):
            source_path = os.path.join(self.script_dir, filename)
            target_path = os.path.join(target_dir, filename)
            if os.path.exists(source_path) and not os.path.exists(target_path):
                shutil.copy2(source_path, target_path)

    def _download_release(self, download_url: str, sha256_value: Optional[str]) -> str:
        """Download a zip release to a temporary file and optionally verify it."""
        request = Request(download_url, headers={'User-Agent': f'SalesforceAuditTool/{self.current_version}'})
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as handle:
            with urlopen(request, timeout=120) as response:
                shutil.copyfileobj(response, handle)
            zip_path = handle.name

        if sha256_value:
            digest = hashlib.sha256()
            with open(zip_path, 'rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest().lower() != sha256_value.lower():
                os.unlink(zip_path)
                raise ValueError("Downloaded release checksum does not match manifest sha256.")

        return zip_path

    @staticmethod
    def _locate_extracted_root(extract_dir: str) -> str:
        """Find the extracted release directory containing the audit entrypoint."""
        direct_script = os.path.join(extract_dir, 'salesforce_audit.py')
        if os.path.exists(direct_script):
            return extract_dir

        for root, _, files in os.walk(extract_dir):
            if 'salesforce_audit.py' in files:
                return root

        raise FileNotFoundError("Downloaded release does not contain salesforce_audit.py")

    def install_release(self, manifest: Dict, settings: Dict) -> str:
        """Install the target release and return the installed directory."""
        latest_version = str(manifest.get('latest_version') or manifest.get('version') or '').strip()
        if not latest_version:
            raise ValueError("Update manifest is missing latest_version.")

        existing_install = self._find_existing_install(latest_version)
        if existing_install:
            self._copy_local_files(existing_install, settings.get('copy_local_config', True))
            return existing_install

        download_url = str(manifest.get('download_url') or '').strip()
        if not download_url:
            raise ValueError("Update manifest is missing download_url.")

        zip_path = None
        temp_extract_dir = None
        try:
            zip_path = self._download_release(
                download_url=download_url,
                sha256_value=manifest.get('sha256') if settings.get('verify_sha256', True) else None
            )
            temp_extract_dir = tempfile.mkdtemp(prefix='sf-audit-update-')

            with zipfile.ZipFile(zip_path, 'r') as archive:
                archive.extractall(temp_extract_dir)

            extracted_root = self._locate_extracted_root(temp_extract_dir)
            install_base = os.path.dirname(self.script_dir)
            final_dir = os.path.join(install_base, os.path.basename(extracted_root.rstrip(os.sep)))

            if os.path.abspath(extracted_root) != os.path.abspath(final_dir):
                if os.path.exists(final_dir):
                    installed_metadata_path = os.path.join(final_dir, 'tool_version.json')
                    if os.path.exists(installed_metadata_path):
                        with open(installed_metadata_path, 'r', encoding='utf-8') as handle:
                            installed_metadata = json.load(handle)
                        installed_version = str(installed_metadata.get('version', '')).strip()
                        if installed_version == latest_version:
                            self._copy_local_files(final_dir, settings.get('copy_local_config', True))
                            return final_dir
                    raise FileExistsError(f"Target install directory already exists: {final_dir}")

                shutil.move(extracted_root, final_dir)
            else:
                final_dir = extracted_root

            self._copy_local_files(final_dir, settings.get('copy_local_config', True))

            requirements_path = os.path.join(final_dir, 'requirements.txt')
            if os.path.exists(requirements_path):
                print("📦 Installing dependencies for the new version...")
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '-r', requirements_path],
                    check=True
                )

            return final_dir
        finally:
            if zip_path and os.path.exists(zip_path):
                os.unlink(zip_path)
            if temp_extract_dir and os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir, ignore_errors=True)

    @staticmethod
    def _should_prompt() -> bool:
        """Return True when user interaction is available."""
        return sys.stdin.isatty() and sys.stdout.isatty()

    @staticmethod
    def _clean_forward_args(argv: List[str]) -> List[str]:
        """Strip updater-only flags before relaunching the target version."""
        cleaned_args = []
        skip_next = False
        for arg in argv:
            if skip_next:
                skip_next = False
                continue

            if arg in {'--skip-update-check', '--yes-update', '--check-updates'}:
                continue

            if arg == '--update-manifest-url':
                skip_next = True
                continue

            if arg.startswith('--update-manifest-url='):
                continue

            cleaned_args.append(arg)

        return cleaned_args

    def maybe_update(self, args) -> Optional[int]:
        """Check for a newer version, optionally install it, and relaunch."""
        if getattr(args, 'skip_update_check', False):
            return None

        settings = self.load_settings(getattr(args, 'update_manifest_url', None))
        if not settings.get('enabled', True):
            if getattr(args, 'check_updates', False):
                print("ℹ️  Automatic updates are disabled.")
                return 0
            return None

        manifest_url = str(settings.get('manifest_url') or '').strip()
        if not manifest_url:
            if getattr(args, 'check_updates', False):
                print("ℹ️  No update manifest configured. Add update_config.json or set SF_AUDIT_UPDATE_MANIFEST_URL.")
                return 0
            return None

        try:
            manifest = self.fetch_manifest(manifest_url)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            print(f"⚠️  Update check failed: {exc}")
            return 0 if getattr(args, 'check_updates', False) else None

        latest_version = str(manifest.get('latest_version') or manifest.get('version') or '').strip()
        if not latest_version:
            print("⚠️  Update manifest is missing latest_version.")
            return 0 if getattr(args, 'check_updates', False) else None

        if not self._is_newer_version(latest_version, self.current_version):
            if getattr(args, 'check_updates', False):
                print(f"✅ You are already on the latest version ({self.current_version}).")
                return 0
            return None

        print(f"⬆️  Update available: v{latest_version} (current: v{self.current_version})")
        if manifest.get('notes_url'):
            print(f"   Release notes: {manifest['notes_url']}")

        if getattr(args, 'check_updates', False) and not getattr(args, 'yes_update', False):
            print("ℹ️  Re-run with --yes-update or start the tool normally to install it.")
            return 0

        should_install = bool(getattr(args, 'yes_update', False) or settings.get('auto_install'))
        if not should_install and settings.get('prompt_for_install', True) and self._should_prompt():
            try:
                user_choice = input("Install the latest version now? [Y/n]: ").strip().lower()
                should_install = user_choice in {'', 'y', 'yes'}
            except (EOFError, KeyboardInterrupt):
                should_install = False

        if not should_install:
            if getattr(args, 'check_updates', False):
                print("ℹ️  Update available but not installed.")
                return 0
            return None

        try:
            install_dir = self.install_release(manifest, settings)
        except (OSError, ValueError, FileNotFoundError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
            print(f"⚠️  Auto-update failed: {exc}")
            return 0 if getattr(args, 'check_updates', False) else None

        print(f"✅ Installed v{latest_version} at: {install_dir}")

        if getattr(args, 'check_updates', False):
            return 0

        next_script = os.path.join(install_dir, 'salesforce_audit.py')
        forward_args = self._clean_forward_args(sys.argv[1:])
        forward_args.append('--skip-update-check')

        print("🚀 Relaunching the latest version...\n")
        result = subprocess.run([sys.executable, next_script] + forward_args)
        return result.returncode


class SalesforceAuditor:
    """Main auditor class that orchestrates the audit process"""
    
    # Category mapping for violation types
    VIOLATION_CATEGORY_MAP = {
        # Performance/Governor Limits
        'SOQL in Loop': 'Performance',
        'DML in Loop': 'Performance',
        'Indirect SOQL in Loop': 'Performance',
        'Indirect DML in Loop': 'Performance',
        'Non-Restrictive Query': 'Performance',
        'CMDT SOQL without Filter': 'Performance',
        'Nested Loops with DML/SOQL': 'Performance',
        'Schema.getGlobalDescribe() in Loop': 'Performance',
        'Schema.getGlobalDescribe() Not Efficient': 'Performance',
        'Redundant SOQL': 'Performance',
        'SObject Map in a For Loop': 'Performance',
        'SOQL with Negative Expressions': 'Performance',
        'SOQL with Unused Fields': 'Performance',
        'SOQL with Wildcard Filter': 'Performance',
        'SOQL Without a WHERE Clause or LIMIT Statement': 'Performance',
        'Unused Methods': 'Best Practices',
        'SOQL with Apex Filter': 'Performance',
        'Expensive Methods in Loop': 'Performance',
        'Expensive String Comparison': 'Performance',
        'Copying Elements with for Loop': 'Best Practices',
        'Sorting in Apex Instead of SOQL ORDER BY': 'Performance',
        'Busy Loop Delay': 'Performance',
        'Limits.getHeapSize() in Loop': 'Performance',
        
        # Architecture/Best Practices
        '@future Method Usage': 'Architecture',
        'Async in Trigger': 'Architecture',
        'EventBus without Callback': 'Best Practices',
        'Mixed DML Operations': 'Architecture',
        
        # Code Quality
        'Hardcoded Salesforce ID': 'Best Practices',
        'Generic Exception Catch': 'Code Quality',
        'Recursive Trigger Risk': 'Code Quality',
        
        # Security
        'Missing CRUD/FLS Check': 'Security',
        'SOQL Injection Risk': 'Security',
        'Missing Sharing Keyword': 'Security',
        'Hardcoded Credentials': 'Security',
        'System.debug with Sensitive Data': 'Security',
        
        # Test Quality
        'Missing Test Assertions': 'Test Quality',
        '@isTest(SeeAllData=true)': 'Test Quality',
        'Missing Persona-Based Testing': 'Test Quality',
        'Test Coverage Below 90%': 'Test Quality',
        'Test Coverage Below 80%': 'Test Quality',
        'Test Coverage Below 75%': 'Test Quality',
    }
    
    @staticmethod
    def get_violation_category(violation_type: str) -> str:
        """
        Get the correct category for a violation type
        
        Args:
            violation_type: The violation type string
            
        Returns:
            Category string
        """
        return SalesforceAuditor.VIOLATION_CATEGORY_MAP.get(violation_type, 'Other')
    
    def __init__(self, config_path: str = None, cli_args: Dict = None):
        """
        Initialize the auditor
        
        Args:
            config_path: Path to configuration file (optional, deprecated)
            cli_args: Command-line arguments to override config
        """
        self.config = self._load_config(config_path, cli_args)
        self._setup_logging()
        
        self.sf_connector = None
        self.sf = None
        self.metadata_retriever = None
        
        # Results storage
        self.metadata_snapshot = {}
        self.all_issues = []
        self.coverage_details = []
        self.data_model_issues = []
        
        self.logger = logging.getLogger(__name__)
    
    def _load_config(self, config_path: str, cli_args: Dict = None) -> Dict:
        """
        Load configuration - uses SFDX by default, no config.yaml required
        CLI arguments override defaults
        """
        # Start with default config (SFDX only)
        config = self._get_default_config()
        
        # Try to load config file if it exists (backward compatibility)
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        # Merge file config into default
                        self._merge_configs(config, file_config)
                print(f"✅ Loaded configuration from: {config_path}")
            except yaml.YAMLError as e:
                print(f"⚠️  Warning: Error parsing config file: {e}")
                print("Using default SFDX authentication...")
        
        # Apply CLI arguments (highest priority)
        if cli_args:
            self._apply_cli_args(config, cli_args)
        
        # Auto-detect SFDX default org if no authentication is configured
        sf_config = config.get('salesforce', {})
        if not sf_config.get('org_alias') and sf_config.get('auth_method') == 'sfdx':
            orgs = self._get_sfdx_orgs()
            if orgs:
                # Find default org or use first available
                default_org = next((org for org in orgs if org.get('isDefaultUsername')), orgs[0])
                sf_config['org_alias'] = default_org.get('alias') or default_org.get('username')
                print(f"ℹ️  Auto-detected SFDX org: {sf_config['org_alias']}")
            else:
                # No SFDX orgs found - prompt user to authenticate
                print("\n" + "="*60)
                print("🔐 AUTHENTICATION REQUIRED")
                print("="*60)
                print("\nNo authenticated Salesforce orgs found.")
                print("\n💡 Please authenticate using one of these options:")
                print("\n  Option 1 (Recommended): Web Browser Login")
                print("  " + "-"*50)
                print("  Run this command to authenticate:")
                print("  \033[1msfdx auth:web:login -a myorg\033[0m")
                print("\n  A browser window will open for secure authentication.")
                print("  After successful login, run this script again.")
                print("\n  Option 2: Interactive Mode")
                print("  " + "-"*50)
                print("  Run: \033[1mpython3 salesforce_audit.py -i\033[0m")
                print("  The script will guide you through authentication.")
                print("\n" + "="*60)
                raise Exception("No authenticated orgs found. Please authenticate using: sfdx auth:web:login -a myorg")
        
        return config
    
    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            'salesforce': {
                'auth_method': 'sfdx',
                'org_alias': None,
                'username': None,
                'password': None,
                'security_token': None,
                'domain': 'login',
                'api_version': '59.0'
            },
            'audit': {
                'coverage': {
                    'org_minimum': 70,
                    'org_good': 80,
                    'org_excellent': 90,
                    'class_minimum': 90,
                    'class_target': 100
                },
                'exclusions': {
                    'exclude_standard': True,
                    'exclude_namespaces': [],
                    'exclude_patterns': [
                        '.*Test$',
                        '^Site.*',  # Site classes
                        '^Community.*',  # Community classes
                        '.*SelfReg.*',  # Self-registration classes
                        '.*ChangePassword.*',  # Change password classes
                        '.*ForgotPassword.*',  # Forgot password classes
                        '.*MyProfile.*',  # My profile classes
                    ]
                },
                'governor_limits': {
                    'check_soql_in_loops': True,
                    'check_dml_in_loops': True,
                    'check_indirect_violations': True,
                    'check_non_restrictive_queries': True
                },
                'data_model': {
                    'check_unused_fields': True,
                    'check_duplicate_fields': True
                },
                'static_analysis': {
                    'enabled': False
                }
            },
            'output': {
                'directory': './audit_reports',
                'filename_template': 'SF_Audit_{org_name}_{timestamp}.xlsx',
                'highlight_critical': True,
                'color_coding': True,
                'generate_markdown': True
            },
            'logging': {
                'level': 'INFO',
                'file': './audit.log',
                'console': True
            }
        }
    
    def _merge_configs(self, target: Dict, source: Dict):
        """Recursively merge source config into target"""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._merge_configs(target[key], value)
            else:
                target[key] = value
    
    def _apply_cli_args(self, config: Dict, cli_args: Dict):
        """Apply command-line arguments to config"""
        sf_config = config['salesforce']
        
        # Authentication method
        if cli_args.get('sfdx'):
            sf_config['auth_method'] = 'sfdx'
            if cli_args.get('org_alias'):
                sf_config['org_alias'] = cli_args['org_alias']
            elif cli_args['sfdx'] != 'default':
                sf_config['org_alias'] = cli_args['sfdx']
            else:
                # Auto-detect default org
                orgs = self._get_sfdx_orgs()
                if orgs:
                    # Use first connected org
                    sf_config['org_alias'] = orgs[0].get('alias') or orgs[0].get('username')
                else:
                    sf_config['org_alias'] = 'default'
        elif cli_args.get('username'):
            sf_config['auth_method'] = 'password'
            sf_config['username'] = cli_args['username']
            sf_config['password'] = cli_args.get('password')
            sf_config['security_token'] = cli_args.get('token')
            sf_config['domain'] = cli_args.get('domain', 'login')
        
        # Interactive mode
        if cli_args.get('interactive'):
            self._interactive_auth_setup(sf_config)
        
        # Output settings
        if cli_args.get('output_dir'):
            config['output']['directory'] = cli_args['output_dir']
        
        if cli_args.get('no_markdown'):
            config['output']['generate_markdown'] = False
        
        # Verbose logging
        if cli_args.get('verbose'):
            config['logging']['level'] = 'DEBUG'
            sf_config['verbose'] = True
    
    def _interactive_auth_setup(self, sf_config: Dict):
        """Interactively prompt user for authentication details"""
        print("\n" + "=" * 60)
        print("INTERACTIVE AUTHENTICATION SETUP")
        print("=" * 60)
        
        # Check for SFDX orgs first
        sfdx_orgs = self._get_sfdx_orgs()
        
        if sfdx_orgs:
            print(f"\n✅ Found {len(sfdx_orgs)} SFDX authenticated org(s):")
            
            # Show available orgs
            default_org = None
            for i, org in enumerate(sfdx_orgs, 1):
                alias = org.get('alias', 'N/A')
                username = org.get('username', 'N/A')
                is_default = org.get('isDefaultUsername', False)
                status = '🟢' if org.get('connectedStatus') == 'Connected' else '🔴'
                default_marker = ' (DEFAULT)' if is_default else ''
                
                print(f"  {i}. {status} {alias} ({username}){default_marker}")
                
                if is_default or default_org is None:
                    default_org = org
            
            print(f"\n💡 Options:")
            print(f"   • Press 1-{len(sfdx_orgs)} to select an org")
            print(f"   • Press Enter to use default org")
            print(f"   • Type 'new' to authenticate a new org (web browser)")
            
            try:
                choice = input("\nYour choice: ").strip().lower()
                
                # Handle 'new' - authenticate a new org
                if choice == 'new':
                    print("\n🔐 Authenticating new org via web browser...")
                    print("A browser window will open for authentication.")
                    new_alias = input("Enter alias for this org [myorg]: ").strip() or 'myorg'
                    
                    try:
                        result = subprocess.run(
                            ['sfdx', 'auth:web:login', '-a', new_alias],
                            timeout=300  # 5 minutes for user to authenticate
                        )
                        
                        if result.returncode == 0:
                            sf_config['auth_method'] = 'sfdx'
                            sf_config['org_alias'] = new_alias
                            print(f"\n✅ Successfully authenticated: {new_alias}")
                            return
                        else:
                            print(f"\n❌ Authentication failed.")
                            print("Please try again or select an existing org.")
                            # Re-run the interactive setup
                            return self._interactive_auth_setup(config)
                    except subprocess.TimeoutExpired:
                        print(f"\n❌ Authentication timed out (5 minutes).")
                        print("Please try again or select an existing org.")
                        return self._interactive_auth_setup(config)
                    except Exception as e:
                        print(f"\n❌ Error during authentication: {str(e)}")
                        print("Please try again or select an existing org.")
                        return self._interactive_auth_setup(config)
                
                # Handle empty (use default)
                elif not choice:
                    if default_org:
                        sf_config['auth_method'] = 'sfdx'
                        sf_config['org_alias'] = default_org.get('alias') or default_org.get('username')
                        print(f"\n✅ Using default org: {sf_config['org_alias']}")
                        return
                    else:
                        print("\n⚠️  No default org found")
                
                # Handle number selection
                elif choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(sfdx_orgs):
                        selected_org = sfdx_orgs[idx]
                        sf_config['auth_method'] = 'sfdx'
                        sf_config['org_alias'] = selected_org.get('alias') or selected_org.get('username')
                        print(f"\n✅ Selected: {sf_config['org_alias']}")
                        return
                    else:
                        print(f"\n⚠️  Invalid selection. Using default org.")
                        if default_org:
                            sf_config['auth_method'] = 'sfdx'
                            sf_config['org_alias'] = default_org.get('alias') or default_org.get('username')
                            print(f"✅ Using: {sf_config['org_alias']}")
                            return
            
            except (EOFError, KeyboardInterrupt):
                print("\n\n⚠️  Interactive mode interrupted.")
                # Try to use default org as fallback
                if default_org:
                    print(f"⚠️  Attempting to use default SFDX org: {default_org.get('alias')}")
                    sf_config['auth_method'] = 'sfdx'
                    sf_config['org_alias'] = default_org.get('alias') or default_org.get('username')
                    return
                else:
                    raise Exception("No SFDX org available and interactive mode was interrupted")
        
        else:
            # No SFDX orgs found - prompt to authenticate
            print("\n⚠️  No SFDX authenticated orgs found")
            print("\n🔐 Let's authenticate via web browser (recommended)...")
            print("A browser window will open for secure authentication.")
            new_alias = input("\nEnter an alias for this org [myorg]: ").strip() or 'myorg'
            
            try:
                print(f"\n🌐 Opening browser for authentication...")
                print("Please complete the login in your browser window.")
                
                result = subprocess.run(
                    ['sfdx', 'auth:web:login', '-a', new_alias],
                    timeout=300
                )
                
                if result.returncode == 0:
                    sf_config['auth_method'] = 'sfdx'
                    sf_config['org_alias'] = new_alias
                    print(f"\n✅ Successfully authenticated: {new_alias}")
                    print("You can now run audits against this org!")
                    return
                else:
                    print(f"\n❌ Authentication failed.")
                    print("Please try running: sfdx auth:web:login -a myorg")
                    print("Then run this script again.")
                    raise Exception("Authentication failed")
            except subprocess.TimeoutExpired:
                print(f"\n❌ Authentication timed out (5 minutes).")
                print("Please try running: sfdx auth:web:login -a myorg")
                print("Then run this script again.")
                raise Exception("Authentication timed out")
            except FileNotFoundError:
                print(f"\n❌ SFDX CLI not found!")
                print("\nPlease install Salesforce CLI:")
                print("  • macOS: brew install sfdx-cli")
                print("  • Windows: Download from https://developer.salesforce.com/tools/sfdxcli")
                print("  • Linux: npm install -g sfdx-cli")
                raise Exception("SFDX CLI not installed")
            except (EOFError, KeyboardInterrupt):
                print("\n\n❌ Interactive mode interrupted.")
                print("To authenticate, run: sfdx auth:web:login -a myorg")
                print("Then run this script again.")
                raise Exception("Interactive mode interrupted")
            except Exception as e:
                print(f"\n❌ Error: {str(e)}")
                print("Please try running: sfdx auth:web:login -a myorg")
                print("Then run this script again.")
                raise
    
    def _get_sfdx_orgs(self) -> List[Dict]:
        """Get list of SFDX authenticated orgs"""
        try:
            result = subprocess.run(
                ['sfdx', 'force:org:list', '--json'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get('status') == 0:
                    non_scratch = data.get('result', {}).get('nonScratchOrgs', [])
                    scratch = data.get('result', {}).get('scratchOrgs', [])
                    all_orgs = non_scratch + scratch
                    
                    # Filter out disconnected orgs
                    connected_orgs = [org for org in all_orgs if org.get('connectedStatus') == 'Connected']
                    
                    return connected_orgs if connected_orgs else all_orgs
        except FileNotFoundError:
            # SFDX CLI not installed
            return []
        except subprocess.TimeoutExpired:
            # Command timed out
            return []
        except json.JSONDecodeError:
            # Invalid JSON response
            return []
        except Exception:
            # Any other error
            return []
        
        return []
    
    def _setup_logging(self):
        """Setup logging configuration"""
        log_config = self.config.get('logging', {})
        
        # Check for verbose flag
        verbose = self.config.get('salesforce', {}).get('verbose', False)
        log_level_str = 'DEBUG' if verbose else log_config.get('level', 'INFO')
        log_level = getattr(logging, log_level_str)
        
        log_format = log_config.get(
            'format',
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Configure root logger
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[]
        )
        
        # Console handler
        if log_config.get('console', True):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level)
            console_handler.setFormatter(logging.Formatter(log_format))
            logging.getLogger().addHandler(console_handler)
        
        # File handler
        if log_config.get('file'):
            file_handler = logging.FileHandler(log_config['file'])
            file_handler.setLevel(log_level)
            file_handler.setFormatter(logging.Formatter(log_format))
            logging.getLogger().addHandler(file_handler)
    
    def connect_to_salesforce(self):
        """Establish connection to Salesforce"""
        self.logger.info("=" * 80)
        self.logger.info("SALESFORCE CODE AUDIT TOOL")
        self.logger.info("=" * 80)
        
        self.sf_connector = SalesforceConnector(self.config['salesforce'])
        self.sf = self.sf_connector.connect()
        self.metadata_retriever = MetadataRetriever(self.sf, self.config)
        
        # Update metadata snapshot with org info
        self.metadata_snapshot['org_name'] = self.sf_connector.get_org_name()
        self.metadata_snapshot['org_type'] = self.sf_connector.get_org_type()
        self.metadata_snapshot['org_domain_name'] = self.sf_connector.get_org_domain_name()
    
    def retrieve_metadata(self):
        """Retrieve all metadata from Salesforce"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("PHASE 1: RETRIEVING METADATA")
        self.logger.info("=" * 80)
        
        snapshot = self.metadata_retriever.get_metadata_snapshot()
        self.metadata_snapshot.update(snapshot)
        
        self.logger.info(f"\n📊 Metadata Summary:")
        self.logger.info(f"  - Apex Classes: {snapshot['apex_classes']}")
        self.logger.info(f"  - Test Classes: {snapshot['test_classes']}")
        self.logger.info(f"  - Triggers: {snapshot['triggers']}")
        self.logger.info(f"  - Custom Objects: {snapshot['custom_objects']}")
        self.logger.info(f"  - Custom Fields: {snapshot['custom_fields']}")
        self.logger.info(f"  - Flows: {snapshot['flows']}")
    
    def _find_trigger_handler(self, trigger_name: str, trigger_body: str, class_coverages: List[Dict]) -> Optional[Dict]:
        """
        Find the handler class for a trigger by analyzing the trigger code.
        Returns the handler's coverage info if found.
        """
        if not trigger_body:
            return None
        
        # Common trigger handler patterns
        handler_patterns = [
            # Pattern 1: ClassName.method() call
            r'(\w+)\.(?:handleBeforeInsert|handleAfterInsert|handleBeforeUpdate|handleAfterUpdate|handleBeforeDelete|handleAfterDelete|handleAfterUndelete|handle|run|execute)\s*\(',
            # Pattern 2: new ClassName() instantiation
            r'new\s+(\w+)\s*\(',
            # Pattern 3: ClassName variable declaration
            r'(\w+Handler|\w+TriggerHandler)\s+\w+\s*=',
        ]
        
        # Extract potential handler class names
        handler_names = set()
        trigger_body_clean = trigger_body.replace('\n', ' ')
        
        for pattern in handler_patterns:
            matches = re.findall(pattern, trigger_body_clean, re.IGNORECASE)
            handler_names.update(matches)
        
        # Common handler naming conventions based on trigger name
        # E.g., AccountTrigger -> AccountTriggerHandler, AccountHandler
        base_name = trigger_name.replace('Trigger', '').replace('trigger', '')
        potential_handlers = [
            f"{base_name}TriggerHandler",
            f"{base_name}Handler",
            f"{base_name}Service",
            f"{base_name}Manager"
        ]
        handler_names.update(potential_handlers)
        
        # Find matching handler in coverage data
        for handler_name in handler_names:
            # Filter out common Salesforce classes
            if handler_name in ['System', 'Trigger', 'Database', 'Test', 'Schema', 'String', 'Integer', 'List', 'Map', 'Set']:
                continue
            
            for class_cov in class_coverages:
                if class_cov['name'].lower() == handler_name.lower():
                    return class_cov
        
        return None
    
    def analyze_test_coverage(self) -> CoverageStats:
        """Analyze test coverage with smart trigger-handler detection"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("PHASE 2: ANALYZING TEST COVERAGE")
        self.logger.info("=" * 80)
        
        org_coverage, class_coverages = self.metadata_retriever.get_test_coverage()
        
        # Get trigger information for handler detection
        triggers = self.metadata_retriever.get_apex_triggers()
        trigger_map = {t.get('Name', ''): t.get('Body', '') for t in triggers if t.get('Name')}
        
        # Calculate statistics
        classes_below_90 = len([c for c in class_coverages if c['coverage_percent'] < 90])
        classes_below_75 = len([c for c in class_coverages if c['coverage_percent'] < 75])
        
        total_classes = len(class_coverages)
        avg_coverage = sum(c['coverage_percent'] for c in class_coverages) / total_classes if total_classes > 0 else 0
        
        coverage_stats = CoverageStats(
            org_coverage=org_coverage,
            classes_below_90=classes_below_90,
            classes_below_75=classes_below_75,
            total_classes=total_classes,
            average_class_coverage=avg_coverage
        )
        
        self.coverage_details = class_coverages
        
        self.logger.info(f"\n📈 Coverage Statistics:")
        self.logger.info(f"  - Org Coverage: {org_coverage:.1f}%")
        self.logger.info(f"  - Average Class Coverage: {avg_coverage:.1f}%")
        self.logger.info(f"  - Classes Below 90%: {classes_below_90}")
        self.logger.info(f"  - Classes Below 75%: {classes_below_75}")
        
        # Flag coverage issues with smart trigger-handler detection
        triggers_skipped = 0
        for class_cov in class_coverages:
            class_name = class_cov['name']
            coverage_pct = class_cov['coverage_percent']
            
            # Check if this is a trigger with low coverage
            if coverage_pct < 75:
                # Check if it's a trigger (name ends with 'Trigger' or check trigger_map)
                is_trigger = class_name in trigger_map or class_name.endswith('Trigger')
                
                if is_trigger:
                    # Try to find the handler class
                    trigger_body = trigger_map.get(class_name, '')
                    handler_cov = self._find_trigger_handler(class_name, trigger_body, class_coverages)
                    
                    if handler_cov and handler_cov['coverage_percent'] >= 75:
                        # Handler has good coverage, skip flagging the trigger
                        self.logger.info(f"  ℹ️  Skipping {class_name} ({coverage_pct:.1f}%) - Handler '{handler_cov['name']}' has {handler_cov['coverage_percent']:.1f}% coverage")
                        triggers_skipped += 1
                        continue
                
                # Flag as low coverage
                self.all_issues.append({
                    'file_name': class_name,
                    'type': 'Coverage',
                    'line_number': 'N/A',
                    'category': 'Test Coverage',
                    'rule_name': 'Test Coverage Below 75%',
                    'criticality': 'Critical',
                    'snippet': f"Coverage: {coverage_pct:.1f}%",
                    'recommendation': f"CRITICAL: Increase test coverage to at least 75% immediately (current: {coverage_pct:.1f}%)"
                })
            elif coverage_pct < 80:
                self.all_issues.append({
                    'file_name': class_name,
                    'type': 'Coverage',
                    'line_number': 'N/A',
                    'category': 'Test Coverage',
                    'rule_name': 'Test Coverage Below 80%',
                    'criticality': 'High',
                    'snippet': f"Coverage: {coverage_pct:.1f}%",
                    'recommendation': f"HIGH: Increase test coverage to at least 80% (current: {coverage_pct:.1f}%)"
                })
            elif coverage_pct < 90:
                self.all_issues.append({
                    'file_name': class_name,
                    'type': 'Coverage',
                    'line_number': 'N/A',
                    'category': 'Test Coverage',
                    'rule_name': 'Test Coverage Below 90%',
                    'criticality': 'Medium',
                    'snippet': f"Coverage: {coverage_pct:.1f}%",
                    'recommendation': f"Increase test coverage to at least 90% (current: {coverage_pct:.1f}%)"
                })
        
        if triggers_skipped > 0:
            self.logger.info(f"  ✅ Skipped {triggers_skipped} trigger(s) with well-tested handler classes")
        
        return coverage_stats
    
    def analyze_apex_code(self):
        """Analyze Apex classes and triggers for governor limits and patterns"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("PHASE 3: ANALYZING APEX CODE")
        self.logger.info("=" * 80)
        
        # Get Apex classes
        classes = self.metadata_retriever.get_apex_classes()
        triggers = self.metadata_retriever.get_apex_triggers()
        
        total_files = len(classes) + len(triggers)
        self.logger.info(f"Analyzing {total_files} files...\n")
        
        violation_count = 0
        
        # Analyze classes
        with tqdm(total=total_files, desc="Analyzing files") as pbar:
            for cls in classes:
                name = cls.get('Name', 'Unknown')
                body = cls.get('Body', '')
                
                violations = analyze_apex_code(name + '.cls', body, is_trigger=False)
                
                for violation in violations:
                    self.all_issues.append({
                        'file_name': violation.file_name,
                        'type': 'Apex Class',
                        'line_number': violation.line_number,
                        'category': self.get_violation_category(violation.violation_type.value),
                        'rule_name': violation.violation_type.value,
                        'criticality': violation.criticality,
                        'snippet': violation.code_snippet[:100],
                        'recommendation': violation.recommendation
                    })
                    violation_count += 1
                
                pbar.update(1)
            
            # Analyze triggers
            for trigger in triggers:
                name = trigger.get('Name', 'Unknown')
                body = trigger.get('Body', '')
                
                violations = analyze_apex_code(name + '.trigger', body, is_trigger=True)
                
                for violation in violations:
                    self.all_issues.append({
                        'file_name': violation.file_name,
                        'type': 'Trigger',
                        'line_number': violation.line_number,
                        'category': self.get_violation_category(violation.violation_type.value),
                        'rule_name': violation.violation_type.value,
                        'criticality': violation.criticality,
                        'snippet': violation.code_snippet[:100],
                        'recommendation': violation.recommendation
                    })
                    violation_count += 1
                
                pbar.update(1)
        
        self.logger.info(f"\n✅ Found {violation_count} code violations")
        
        # Also analyze test classes for test-specific checks
        self.analyze_test_classes()
    
    def analyze_test_classes(self):
        """Analyze test classes for test-specific patterns (assertions, persona testing, etc.)"""
        # Get ALL Apex classes (including test classes) without exclusions
        all_classes_query = """
            SELECT Id, Name, Body, LengthWithoutComments, ApiVersion
            FROM ApexClass
            WHERE NamespacePrefix = null
            ORDER BY Name
        """
        
        try:
            all_classes = self.metadata_retriever.sf.query_all(all_classes_query)
            all_classes_list = all_classes.get('records', [])
            
            # Filter to only test classes
            test_classes = []
            for cls in all_classes_list:
                body = cls.get('Body', '').lower()
                if '@istest' in body or 'testmethod' in body:
                    test_classes.append(cls)
            
            if not test_classes:
                return
            
            self.logger.info(f"Analyzing {len(test_classes)} test classes for test quality...")
            
            # Analyze each test class
            for cls in test_classes:
                name = cls.get('Name', 'Unknown')
                body = cls.get('Body', '')
                
                violations = analyze_apex_code(name + '.cls', body, is_trigger=False)
                
                for violation in violations:
                    test_quality_criticality = 'High' if violation.criticality == 'Critical' else violation.criticality
                    self.all_issues.append({
                        'file_name': violation.file_name,
                        'type': 'Test Class',
                        'line_number': violation.line_number,
                        'category': 'Test Quality',
                        'rule_name': violation.violation_type.value,
                        'criticality': test_quality_criticality,
                        'snippet': violation.code_snippet[:100],
                        'recommendation': violation.recommendation
                    })
            
            self.logger.info(f"✅ Analyzed {len(test_classes)} test classes")
            
        except Exception as e:
            self.logger.warning(f"Could not analyze test classes: {e}")
    
    def run_static_analysis(self):
        """Run static analysis tools (PMD, SFDX Scanner)"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("PHASE 4: STATIC ANALYSIS")
        self.logger.info("=" * 80)
        
        if not self.config.get('audit', {}).get('static_analysis', {}).get('enabled', True):
            self.logger.info("Static analysis disabled in configuration")
            return
        
        # Note: Static analysis would require local source code
        # This is a placeholder for the implementation
        self.logger.warning("Static analysis requires local source code - skipping")
        self.logger.info("To enable: Download metadata and configure PMD/Scanner paths")
    
    def analyze_data_model(self):
        """Analyze data model for unused/duplicate fields"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("PHASE 5: DATA MODEL ANALYSIS")
        self.logger.info("=" * 80)
        
        if not self.config.get('audit', {}).get('data_model', {}).get('check_unused_fields', True):
            self.logger.info("Data model analysis disabled")
            return
        
        # Get custom fields
        fields = self.metadata_retriever.get_custom_fields()
        
        self.logger.info(f"Analyzing {len(fields)} custom fields...")
        
        # Note: Detecting unused fields requires analyzing all references
        # This is a simplified implementation
        self.logger.warning("Full unused field detection requires comprehensive code analysis")
        self.logger.info("Checking for duplicate field names...")
        
        # Check for duplicate field names
        field_map = {}
        for field in fields:
            obj_name = field.get('EntityDefinition', {}).get('QualifiedApiName', 'Unknown')
            field_name = field.get('QualifiedApiName', '')
            field_label = field.get('Label', '')
            
            key = f"{obj_name}.{field_label}"
            
            if key in field_map:
                self.data_model_issues.append({
                    'object_name': obj_name,
                    'field_name': field_name,
                    'issue_type': 'Duplicate Label',
                    'impact': f"Same label as {field_map[key]}",
                    'recommendation': 'Review if these fields serve different purposes'
                })
            else:
                field_map[key] = field_name
        
        self.logger.info(f"Found {len(self.data_model_issues)} data model issues")
    
    def analyze_lwc(self):
        """Analyze Lightning Web Components for security and best practices"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("PHASE 6: ANALYZING LIGHTNING WEB COMPONENTS")
        self.logger.info("=" * 80)
        
        if not self.config.get('audit', {}).get('ui', {}).get('check_double_click_prevention', True):
            self.logger.info("LWC analysis disabled in configuration")
            return
        
        # Get LWC components with source code
        lwc_components = self.metadata_retriever.get_lwc_components()
        
        if not lwc_components:
            self.logger.info("No LWC components found")
            return
        
        self.logger.info(f"Analyzing {len(lwc_components)} LWC components for security and best practices...")
        
        lwc_violations = 0
        components_analyzed = 0
        
        # Analyze each component
        with tqdm(total=len(lwc_components), desc="Analyzing LWC components") as pbar:
            for component in lwc_components:
                name = component.get('DeveloperName', 'Unknown')
                js_code = component.get('js_code', '')
                html_code = component.get('html_code', '')
                
                # Only analyze if we have source code
                if js_code or html_code:
                    issues = analyze_lwc_component(name, js_code, html_code)
                    
                    for issue in issues:
                        self.all_issues.append(issue)
                        lwc_violations += 1
                    
                    components_analyzed += 1
                
                pbar.update(1)
        
        self.logger.info(f"\n✅ Analyzed {components_analyzed} LWC components")
        self.logger.info(f"Found {lwc_violations} LWC security/best practice violations")
        
        if components_analyzed < len(lwc_components):
            self.logger.warning(f"Note: Source code retrieved for {components_analyzed} of {len(lwc_components)} components")
            self.logger.info("For complete LWC analysis, consider downloading all metadata")
    
    def calculate_grade(self, coverage_stats: CoverageStats):
        """Calculate overall grade and generate results"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("PHASE 8: CALCULATING GRADE")
        self.logger.info("=" * 80)
        
        # Count issues by criticality
        issue_counts = IssueCounts()
        
        for issue in self.all_issues:
            criticality = issue.get('criticality', 'Low')
            if criticality == 'Critical':
                issue_counts.critical += 1
            elif criticality == 'High':
                issue_counts.high += 1
            elif criticality == 'Medium':
                issue_counts.medium += 1
            else:
                issue_counts.low += 1
        
        # Check for SOQL/DML in loops
        has_loops = any(
            issue.get('rule_name') in ['SOQL in Loop', 'DML in Loop', 'Indirect SOQL in Loop', 'Indirect DML in Loop']
            for issue in self.all_issues
        )
        
        # Calculate grade
        grading_engine = GradingEngine(self.config.get('grading'))
        grading_result = grading_engine.calculate_grade(
            issue_counts=issue_counts,
            coverage_stats=coverage_stats,
            has_soql_dml_in_loops=has_loops
        )
        
        # Generate top priority fixes
        grading_result.top_priority_fixes = grading_engine.generate_priority_fixes(
            self.all_issues,
            top_n=5
        )
        
        # Log results
        self.logger.info(f"\n🎯 FINAL GRADE: {grading_result.grade.value}")
        self.logger.info(f"\n📋 Issue Summary:")
        self.logger.info(f"  - Critical: {issue_counts.critical}")
        self.logger.info(f"  - High: {issue_counts.high}")
        self.logger.info(f"  - Medium: {issue_counts.medium}")
        self.logger.info(f"  - Low: {issue_counts.low}")
        self.logger.info(f"  - Total: {issue_counts.total()}")
        
        return grading_result
    
    def generate_reports(self, grading_result):
        """Generate Excel and Markdown reports"""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("PHASE 9: GENERATING REPORTS")
        self.logger.info("=" * 80)
        
        org_name = self.metadata_snapshot.get('org_name', 'Unknown')
        
        # Generate Excel report
        excel_generator = ExcelReportGenerator(self.config.get('output'))
        excel_path = excel_generator.generate_report(
            org_name=org_name,
            grading_result=grading_result,
            metadata_snapshot=self.metadata_snapshot,
            detailed_issues=self.all_issues,
            data_model_issues=self.data_model_issues,
            coverage_details=self.coverage_details
        )
        
        # Generate Markdown summary
        if self.config.get('output', {}).get('generate_markdown', True):
            markdown_generator = MarkdownReportGenerator()
            markdown_path = markdown_generator.generate_summary(
                org_name=org_name,
                grading_result=grading_result,
                output_dir=self.config.get('output', {}).get('directory', './audit_reports')
            )
        
        # Generate PDF Executive Summary
        if self.config.get('output', {}).get('generate_pdf', True):
            pdf_generator = PDFReportGenerator()
            pdf_path = pdf_generator.generate_executive_summary(
                org_name=org_name,
                grading_result=grading_result,
                metadata_snapshot=self.metadata_snapshot,
                output_dir=self.config.get('output', {}).get('directory', './audit_reports')
            )
        
        self.logger.info(f"\n✅ Reports generated successfully!")
        self.logger.info(f"  - Excel: {excel_path}")
        if self.config.get('output', {}).get('generate_markdown', True):
            self.logger.info(f"  - Markdown: {markdown_path}")
        if self.config.get('output', {}).get('generate_pdf', True) and pdf_path:
            self.logger.info(f"  - PDF Executive Summary: {pdf_path}")
    
    def run(self):
        """Run the complete audit process"""
        try:
            # Phase 1: Connect
            self.connect_to_salesforce()
            
            # Phase 2: Retrieve metadata
            self.retrieve_metadata()
            
            # Phase 3: Analyze coverage
            coverage_stats = self.analyze_test_coverage()
            
            # Phase 4: Analyze Apex code
            self.analyze_apex_code()
            
            # Phase 5: Static analysis (optional)
            self.run_static_analysis()
            
            # Phase 6: Data model analysis
            self.analyze_data_model()
            
            # Phase 7: LWC analysis
            self.analyze_lwc()
            
            # Phase 8: Calculate grade
            grading_result = self.calculate_grade(coverage_stats)
            
            # Phase 9: Generate reports
            self.generate_reports(grading_result)
            
            self.logger.info("\n" + "=" * 80)
            self.logger.info("AUDIT COMPLETE!")
            self.logger.info("=" * 80)
            self.logger.info(f"\n🎯 Final Grade: {grading_result.grade.value}")
            self.logger.info("\nThank you for using Salesforce Code Audit Tool!")
            
        except KeyboardInterrupt:
            self.logger.warning("\n\n❌ Audit interrupted by user")
            sys.exit(1)
        except Exception as e:
            error_msg = str(e)
            
            # Check if it's an authentication error
            if 'INVALID_LOGIN' in error_msg or 'authentication' in error_msg.lower() or 'connect' in error_msg.lower():
                self.logger.error(f"\n\n❌ Authentication Failed: {error_msg}")
                self._print_auth_help(error_msg)
            else:
                self.logger.error(f"\n\n❌ Audit failed: {error_msg}", exc_info=True)
            
            sys.exit(1)
    
    def _print_auth_help(self, error_msg: str):
        """Print helpful authentication troubleshooting"""
        print("\n" + "="*80)
        print("🔧 AUTHENTICATION TROUBLESHOOTING")
        print("="*80)
        
        if 'INVALID_LOGIN' in error_msg:
            print("\n❌ Invalid Login Error - Common causes:\n")
            
            auth_method = self.config.get('salesforce', {}).get('auth_method', 'unknown')
            
            if auth_method == 'password':
                print("1. MISSING SECURITY TOKEN (Most Common)")
                print("   - Security token is REQUIRED for password authentication")
                print("   - Get it: Setup → Personal Info → Reset Security Token")
                print("   - Add to config.yaml under 'security_token'")
                
                token = self.config.get('salesforce', {}).get('security_token', '')
                if not token:
                    print("   - ⚠️  YOUR CONFIG HAS NO SECURITY TOKEN!")
                
                print("\n2. WRONG DOMAIN")
                domain = self.config.get('salesforce', {}).get('domain', 'login')
                print(f"   - Current domain: {domain}")
                print("   - Use 'login' for production/developer orgs")
                print("   - Use 'test' for sandbox orgs")
                
                print("\n3. ACCOUNT LOCKED")
                print("   - Too many failed attempts")
                print("   - Wait 30 minutes or contact admin")
                
                print("\n4. IP RESTRICTIONS")
                print("   - Your org may have IP whitelist enabled")
                print("   - Add your IP or use SFDX authentication")
            
            elif auth_method == 'sfdx':
                print("SFDX Authentication Issue:")
                print("   - Your SFDX session may have expired")
                print("   - Re-authenticate: sfdx auth:web:login -a myorg")
                
                org_alias = self.config.get('salesforce', {}).get('org_alias', 'unknown')
                print(f"   - Current org alias: {org_alias}")
                print("   - Verify: sfdx force:org:list")
        
        print("\n" + "-"*80)
        print("💡 RECOMMENDED SOLUTION:")
        print("-"*80)
        print("\nRun the interactive credential helper:")
        print("\n  python credential_helper.py\n")
        print("This will guide you through setup and test your connection.")
        print("\nOr see detailed troubleshooting: TROUBLESHOOTING.md")
        print("="*80 + "\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Salesforce Code Audit Tool - Analyze org code quality, coverage, security & performance',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode - select from SFDX orgs or enter credentials
  python salesforce_audit.py --interactive
  python salesforce_audit.py -i
  
  # Use specific SFDX org
  python salesforce_audit.py --sfdx myorg
  python salesforce_audit.py -s myorg
  
  # Auto-detect default SFDX org
  python salesforce_audit.py --sfdx
  
  # Use username/password
  python salesforce_audit.py --username user@example.com
  python salesforce_audit.py -u user@example.com
  
  # Use username/password with prompt for password
  python salesforce_audit.py -u user@example.com --prompt-password
  
  # Run with config file (traditional method)
  python salesforce_audit.py --config my_config.yaml
  
  # Show version
  python salesforce_audit.py --version

  # Check whether a newer version is available
  python salesforce_audit.py --check-updates

Authentication Methods (in order of precedence):
  1. Command-line arguments (--sfdx, --username)
  2. Interactive mode (--interactive)
  3. Config file (--config)
  4. Default config.yaml (if exists)
  5. Auto-detect default SFDX org
        """
    )
    
    # Configuration
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to configuration file (optional if using CLI auth)'
    )
    
    # Authentication - SFDX
    parser.add_argument(
        '--sfdx', '-s',
        nargs='?',
        const='default',
        metavar='ORG_ALIAS',
        help='Use SFDX authentication. Optionally specify org alias (default: auto-detect)'
    )
    
    # Authentication - Username/Password
    parser.add_argument(
        '--username', '-u',
        help='Salesforce username'
    )
    
    parser.add_argument(
        '--password', '-p',
        help='Salesforce password (not recommended, use --prompt-password instead)'
    )
    
    parser.add_argument(
        '--prompt-password',
        action='store_true',
        help='Prompt for password securely (recommended over --password)'
    )
    
    parser.add_argument(
        '--token', '-t',
        help='Security token (if required)'
    )
    
    parser.add_argument(
        '--domain', '-d',
        choices=['login', 'test'],
        default='login',
        help='Salesforce domain: login (production) or test (sandbox)'
    )
    
    # Interactive mode
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Interactive mode: prompt for authentication details'
    )
    
    # Output options
    parser.add_argument(
        '--output-dir', '-o',
        help='Output directory for reports (default: ./audit_reports)'
    )
    
    parser.add_argument(
        '--no-markdown',
        action='store_true',
        help='Skip markdown summary generation'
    )
    
    # Misc
    parser.add_argument(
        '--version',
        action='version',
        version=f'Salesforce Code Audit Tool v{TOOL_VERSION}'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output (DEBUG level)'
    )

    parser.add_argument(
        '--check-updates',
        action='store_true',
        help='Check the configured update manifest and exit'
    )

    parser.add_argument(
        '--update-manifest-url',
        help='Override the update manifest URL for this run'
    )

    parser.add_argument(
        '--yes-update',
        action='store_true',
        help='Install an available update without prompting'
    )

    parser.add_argument(
        '--skip-update-check',
        action='store_true',
        help=argparse.SUPPRESS
    )
    
    args = parser.parse_args()

    updater = SelfUpdater(script_dir=SCRIPT_DIR, current_version=TOOL_VERSION)
    update_exit_code = updater.maybe_update(args)
    if update_exit_code is not None:
        sys.exit(update_exit_code)
    
    # Handle password prompt
    if args.username and args.prompt_password and not args.password:
        args.password = getpass.getpass("Enter Salesforce password: ")
    
    # Prepare CLI arguments dict
    cli_args = {
        'sfdx': args.sfdx,
        'org_alias': args.sfdx if args.sfdx and args.sfdx != 'default' else None,
        'username': args.username,
        'password': args.password,
        'token': args.token,
        'domain': args.domain,
        'interactive': args.interactive,
        'output_dir': args.output_dir,
        'no_markdown': args.no_markdown,
        'verbose': args.verbose
    }
    
    # Run audit
    auditor = SalesforceAuditor(config_path=args.config, cli_args=cli_args)
    auditor.run()


if __name__ == "__main__":
    main()

