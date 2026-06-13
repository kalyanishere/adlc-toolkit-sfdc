"""
Salesforce Utilities Module
Handles connection, metadata retrieval, and data extraction from Salesforce
"""

import json
import subprocess
import logging
from typing import Dict, List, Optional, Tuple
from simple_salesforce import Salesforce
from datetime import datetime


logger = logging.getLogger(__name__)


class SalesforceConnector:
    """Handles Salesforce authentication and connection"""
    
    def __init__(self, config: Dict):
        """
        Initialize Salesforce connector
        
        Args:
            config: Salesforce configuration from config.yaml
        """
        self.config = config
        self.sf = None
        self.org_info = {}
        self.instance_url = None
    
    def connect(self) -> Salesforce:
        """
        Connect to Salesforce using configured authentication method
        
        Returns:
            Salesforce connection object
        """
        auth_method = self.config.get('auth_method', 'sfdx')
        
        logger.info(f"Connecting to Salesforce using {auth_method} authentication...")
        
        if auth_method == 'sfdx':
            self.sf = self._connect_sfdx()
        elif auth_method == 'password':
            self.sf = self._connect_password()
        elif auth_method == 'jwt':
            self.sf = self._connect_jwt()
        else:
            raise ValueError(f"Unsupported auth method: {auth_method}")
        
        # Get org info
        self._fetch_org_info()
        
        logger.info(f"✅ Connected to org: {self.org_info.get('Name', 'Unknown')}")
        return self.sf
    
    def _connect_sfdx(self) -> Salesforce:
        """Connect using SFDX CLI"""
        org_alias = self.config.get('org_alias', 'default')
        
        try:
            # Get org info from SFDX
            result = subprocess.run(
                ['sfdx', 'force:org:display', '--targetusername', org_alias, '--json'],
                capture_output=True,
                text=True,
                check=True
            )
            
            org_data = json.loads(result.stdout)
            
            if org_data['status'] != 0:
                raise Exception(f"SFDX error: {org_data.get('message', 'Unknown error')}")
            
            result_data = org_data['result']
            self.instance_url = result_data.get('instanceUrl')
            
            # Connect using access token
            sf = Salesforce(
                instance_url=self.instance_url,
                session_id=result_data['accessToken'],
                version=self.config.get('api_version', '59.0')
            )
            
            return sf
            
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to connect via SFDX: {e.stderr}")
        except FileNotFoundError:
            raise Exception("SFDX CLI not found. Please install Salesforce CLI.")
    
    def _connect_password(self) -> Salesforce:
        """Connect using username/password"""
        username = self.config.get('username')
        password = self.config.get('password')
        security_token = self.config.get('security_token', '')
        domain = self.config.get('domain', 'login')
        
        # Validate required fields
        if not username:
            raise Exception("Username is missing in configuration. Please update config.yaml")
        if not password:
            raise Exception("Password is missing in configuration. Please update config.yaml")
        
        # Warning if security token is empty
        if not security_token:
            logger.warning("⚠️  Security token is empty - this may cause authentication to fail")
            logger.warning("   Most orgs require a security token for password authentication")
            logger.warning("   Get it from: Setup → My Personal Information → Reset Security Token")
        
        try:
            sf = Salesforce(
                username=username,
                password=password,
                security_token=security_token,
                domain=domain,
                version=self.config.get('api_version', '59.0')
            )
            sf_instance = getattr(sf, 'sf_instance', '')
            if sf_instance:
                self.instance_url = f"https://{sf_instance}"
            return sf
        except Exception as e:
            error_msg = str(e)
            
            # Provide more helpful error messages
            if 'INVALID_LOGIN' in error_msg:
                detailed_msg = f"Failed to connect with password: {error_msg}\n\n"
                detailed_msg += "Common causes:\n"
                detailed_msg += "  1. Missing or wrong security token (most common)\n"
                detailed_msg += "  2. Wrong domain (use 'login' for prod, 'test' for sandbox)\n"
                detailed_msg += "  3. Account locked (too many failed attempts)\n"
                detailed_msg += "  4. IP restrictions enabled in org\n\n"
                detailed_msg += "Current config:\n"
                detailed_msg += f"  - Username: {username}\n"
                detailed_msg += f"  - Domain: {domain}.salesforce.com\n"
                detailed_msg += f"  - Security Token: {'Set' if security_token else 'EMPTY ⚠️'}\n\n"
                detailed_msg += "To fix: Run 'python credential_helper.py' for guided setup"
                raise Exception(detailed_msg)
            else:
                raise Exception(f"Failed to connect with password: {error_msg}")
    
    def _connect_jwt(self) -> Salesforce:
        """Connect using JWT bearer flow"""
        # Note: This requires additional JWT libraries
        raise NotImplementedError("JWT authentication not yet implemented")
    
    def _fetch_org_info(self):
        """Fetch organization information"""
        try:
            query = "SELECT Id, Name, OrganizationType, InstanceName FROM Organization LIMIT 1"
            result = self.sf.query(query)
            
            if result['records']:
                self.org_info = result['records'][0]
        except Exception as e:
            logger.warning(f"Could not fetch org info: {str(e)}")
            self.org_info = {'Name': 'Unknown'}
    
    def get_org_name(self) -> str:
        """Get organization name"""
        return self.org_info.get('Name', 'Unknown')
    
    def get_org_type(self) -> str:
        """Get organization type"""
        return self.org_info.get('OrganizationType', 'Unknown')

    def get_org_domain_name(self) -> str:
        """Get the Salesforce org domain/host name"""
        if self.instance_url:
            return self.instance_url.replace('https://', '').replace('http://', '')
        sf_instance = getattr(self.sf, 'sf_instance', '')
        return sf_instance or 'Unknown'


class MetadataRetriever:
    """Retrieves metadata from Salesforce"""
    
    def __init__(self, sf: Salesforce, config: Dict):
        """
        Initialize metadata retriever
        
        Args:
            sf: Salesforce connection
            config: Configuration dictionary
        """
        self.sf = sf
        self.config = config
    
    def get_apex_classes(self) -> List[Dict]:
        """
        Retrieve all Apex classes
        
        Returns:
            List of Apex class metadata
        """
        logger.info("Retrieving Apex classes...")
        
        query = """
            SELECT Id, Name, Body, ApiVersion, Status, IsValid, 
                   LengthWithoutComments, CreatedDate, LastModifiedDate
            FROM ApexClass
            WHERE NamespacePrefix = null
            ORDER BY Name
        """
        
        results = self._query_all(query)
        logger.info(f"Retrieved {len(results)} Apex classes")
        
        # Add total line count (including comments) by counting lines in Body
        for result in results:
            body = result.get('Body', '')
            if body:
                # Count total lines including comments
                total_lines = body.count('\n') + 1  # +1 for last line if no trailing newline
                result['TotalLines'] = total_lines
                result['CommentLines'] = total_lines - (result.get('LengthWithoutComments', 0))
            else:
                result['TotalLines'] = 0
                result['CommentLines'] = 0
        
        # Filter out excluded patterns
        filtered = self._filter_by_exclusions(results)
        logger.info(f"After exclusions: {len(filtered)} Apex classes")
        
        return filtered
    
    def get_apex_triggers(self) -> List[Dict]:
        """Retrieve all Apex triggers"""
        logger.info("Retrieving Apex triggers...")
        
        query = """
            SELECT Id, Name, TableEnumOrId, Body, ApiVersion, Status,
                   UsageBeforeInsert, UsageAfterInsert, UsageBeforeUpdate,
                   UsageAfterUpdate, UsageBeforeDelete, UsageAfterDelete,
                   UsageAfterUndelete
            FROM ApexTrigger
            WHERE NamespacePrefix = null
            ORDER BY Name
        """
        
        results = self._query_all(query)
        logger.info(f"Retrieved {len(results)} triggers")
        
        # Add total line count (including comments) for triggers as well
        for result in results:
            body = result.get('Body', '')
            if body:
                # Count total lines including comments
                total_lines = body.count('\n') + 1
                result['TotalLines'] = total_lines
                # Triggers don't have LengthWithoutComments in the query, but we can estimate
                # or just set TotalLines for consistency
            else:
                result['TotalLines'] = 0
        
        return self._filter_by_exclusions(results)
    
    def get_test_coverage(self) -> Tuple[float, List[Dict]]:
        """
        Get test coverage information using Tooling API
        
        Returns:
            Tuple of (org_coverage_percent, list of class coverages)
        """
        logger.info("Retrieving test coverage...")
        
        try:
            # Get ALL coverage data in a single query (much faster than looping)
            coverage_query = """
                SELECT ApexClassOrTrigger.Name, ApexClassOrTriggerId,
                       NumLinesCovered, NumLinesUncovered
                FROM ApexCodeCoverageAggregate
            """
            
            coverage_records = self._query_all(coverage_query, tooling_api=True)
            logger.info(f"Retrieved {len(coverage_records)} coverage records from Tooling API")
            
            # Site and Community related standard classes to exclude
            excluded_prefixes = [
                'Site',
                'Community',
                'SiteLogin',
                'CommunitiesLanding',
                'CommunitiesSelfReg',
                'ChangePassword',
                'ForgotPassword',
                'MyProfile',
                'SelfRegister'
            ]
            
            class_coverages = []
            total_covered = 0
            total_lines = 0
            excluded_count = 0
            
            for record in coverage_records:
                covered = record.get('NumLinesCovered', 0)
                uncovered = record.get('NumLinesUncovered', 0)
                total = covered + uncovered
                
                # Get class name safely
                class_name = 'Unknown'
                if record.get('ApexClassOrTrigger'):
                    class_name = record['ApexClassOrTrigger'].get('Name', 'Unknown')
                
                # Check if class should be excluded (Site/Community classes)
                should_exclude = any(class_name.startswith(prefix) for prefix in excluded_prefixes)
                
                if should_exclude:
                    excluded_count += 1
                    logger.debug(f"Excluding Site/Community class from coverage: {class_name}")
                    continue
                
                if total > 0:
                    coverage_percent = (covered / total * 100)
                    
                    class_coverages.append({
                        'id': record.get('ApexClassOrTriggerId', ''),
                        'name': class_name,
                        'coverage_percent': coverage_percent,
                        'lines_covered': covered,
                        'lines_not_covered': uncovered,
                        'type': 'Class'
                    })
                    
                    total_covered += covered
                    total_lines += total
            
            if excluded_count > 0:
                logger.info(f"Excluded {excluded_count} Site/Community classes from coverage analysis")
            
            # Calculate org-wide coverage
            org_coverage = (total_covered / total_lines * 100) if total_lines > 0 else 0
            
            if len(coverage_records) == 0:
                logger.warning("No test coverage data found. Have tests been run in this org?")
            
        except Exception as e:
            logger.error(f"Could not retrieve coverage: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # Fallback
            org_coverage = 0
            class_coverages = []
        
        logger.info(f"Org coverage: {org_coverage:.1f}%")
        logger.info(f"Retrieved coverage for {len(class_coverages)} classes/triggers")
        
        return org_coverage, class_coverages
    
    def get_custom_objects(self) -> List[Dict]:
        """Retrieve custom objects using EntityDefinition"""
        logger.info("Retrieving custom objects...")
        
        try:
            query = """
                SELECT QualifiedApiName, Label, DeveloperName
                FROM EntityDefinition
                WHERE QualifiedApiName LIKE '%__c'
                AND IsCustomizable = true
                ORDER BY QualifiedApiName
            """
            
            results = self._query_all(query)
            logger.info(f"Retrieved {len(results)} custom objects")
            
            return results
        except Exception as e:
            logger.error(f"Could not retrieve custom objects: {str(e)}")
            return []
    
    def get_custom_fields(self, object_names: List[str] = None) -> List[Dict]:
        """
        Retrieve custom fields using FieldDefinition
        
        Args:
            object_names: Optional list of object names to filter by
        
        Returns:
            List of custom field metadata
        """
        logger.info("Retrieving custom fields...")
        
        try:
            query = """
                SELECT QualifiedApiName, Label, DeveloperName, 
                       DataType, EntityDefinition.QualifiedApiName
                FROM FieldDefinition
                WHERE QualifiedApiName LIKE '%__c'
                AND EntityDefinition.QualifiedApiName LIKE '%__c'
                ORDER BY EntityDefinition.QualifiedApiName, QualifiedApiName
            """
            
            results = self._query_all(query)
            logger.info(f"Retrieved {len(results)} custom fields")
            
            return results
        except Exception as e:
            logger.error(f"Could not retrieve custom fields: {str(e)}")
            return []
    
    def get_flows(self) -> List[Dict]:
        """Retrieve Flow definitions"""
        logger.info("Retrieving Flows...")
        
        try:
            # Try with available fields only
            query = """
                SELECT DurableId, ApiName, Label, ProcessType, Description
                FROM FlowDefinitionView
                WHERE IsTemplate = false
                ORDER BY ApiName
            """
            
            results = self._query_all(query)
            logger.info(f"Retrieved {len(results)} flows")
            
            return results
        except Exception as e:
            logger.warning(f"Could not retrieve flows: {str(e)}")
            return []
    
    def get_lwc_components(self) -> List[Dict]:
        """Retrieve Lightning Web Components with source code using Tooling API"""
        logger.info("Retrieving LWC components...")
        
        try:
            import requests
            headers = {
                'Authorization': f'Bearer {self.sf.session_id}',
                'Content-Type': 'application/json'
            }
            
            # First get list of LWC bundles
            url = f"{self.sf.base_url}tooling/query/?q=SELECT+Id,DeveloperName,MasterLabel,CreatedDate,LastModifiedDate+FROM+LightningComponentBundle+WHERE+NamespacePrefix=null"
            
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                components = data.get('records', [])
                logger.info(f"Retrieved {len(components)} LWC component bundles")
                
                # Get source code for components (limit to first 50 for performance)
                components_with_source = []
                for i, component in enumerate(components[:50], 1):  # Limit to 50 to avoid timeout
                    component_id = component['Id']
                    
                    # Get component resources (JS, HTML, etc.)
                    resources_url = f"{self.sf.base_url}tooling/query/?q=SELECT+Id,FilePath,Format,Source+FROM+LightningComponentResource+WHERE+LightningComponentBundleId='{component_id}'"
                    
                    try:
                        res_response = requests.get(resources_url, headers=headers, timeout=10)
                        if res_response.status_code == 200:
                            res_data = res_response.json()
                            resources = res_data.get('records', [])
                            
                            js_code = ""
                            html_code = ""
                            
                            for resource in resources:
                                file_path = resource.get('FilePath', '')
                                source = resource.get('Source', '')
                                
                                if file_path.endswith('.js'):
                                    js_code = source
                                elif file_path.endswith('.html'):
                                    html_code = source
                            
                            component['js_code'] = js_code
                            component['html_code'] = html_code
                            components_with_source.append(component)
                            
                            if i % 10 == 0:
                                logger.info(f"Retrieved source for {i}/{min(50, len(components))} LWC components...")
                    except Exception as e:
                        logger.debug(f"Could not get source for {component.get('DeveloperName')}: {str(e)}")
                        continue
                
                logger.info(f"Retrieved source code for {len(components_with_source)} LWC components")
                return components_with_source if components_with_source else components
            else:
                logger.warning(f"Could not retrieve LWC components: HTTP {response.status_code}")
                return []
        except Exception as e:
            logger.warning(f"Could not retrieve LWC components: {str(e)}")
            return []
    
    def get_metadata_snapshot(self) -> Dict:
        """
        Get complete metadata snapshot
        
        Returns:
            Dictionary with counts and metadata
        """
        logger.info("Generating metadata snapshot...")
        
        # Get all classes BEFORE applying exclusions to count test classes accurately
        logger.info("Retrieving Apex classes for metadata snapshot...")
        query = """
            SELECT Id, Name, Body, ApiVersion, Status, IsValid, 
                   LengthWithoutComments, CreatedDate, LastModifiedDate
            FROM ApexClass
            WHERE NamespacePrefix = null
            ORDER BY Name
        """
        all_classes_unfiltered = self._query_all(query)
        logger.info(f"Retrieved {len(all_classes_unfiltered)} total Apex classes (unfiltered)")
        
        # Count test classes from ALL classes (before exclusions)
        test_classes = []
        for c in all_classes_unfiltered:
            body = c.get('Body', '').lower()
            # Check for @isTest annotation or testMethod keyword
            if '@istest' in body or 'testmethod' in body:
                test_classes.append(c)
        
        logger.info(f"Found {len(test_classes)} test classes (before exclusions)")
        
        # Now get filtered classes for reporting
        classes = self.get_apex_classes()
        triggers = self.get_apex_triggers()
        objects = self.get_custom_objects()
        fields = self.get_custom_fields()
        flows = self.get_flows()
        lwc = self.get_lwc_components()
        
        snapshot = {
            'audit_timestamp': datetime.now().isoformat(),
            'api_version': self.config.get('salesforce', {}).get('api_version', 'Unknown'),
            'apex_classes': len(classes),
            'test_classes': len(test_classes),
            'triggers': len(triggers),
            'custom_objects': len(objects),
            'custom_fields': len(fields),
            'flows': len(flows),
            'lwc_components': len(lwc),
            'aura_components': 0,  # Would need additional Tooling API query
        }
        
        logger.info("Metadata snapshot complete")
        return snapshot
    
    def _query_all(self, query: str, tooling_api: bool = False) -> List[Dict]:
        """
        Execute SOQL query and return all results
        
        Args:
            query: SOQL query string
            tooling_api: If True, use Tooling API; otherwise use standard API
        """
        results = []
        
        try:
            if tooling_api:
                # Use requests directly for Tooling API
                import requests
                headers = {
                    'Authorization': f'Bearer {self.sf.session_id}',
                    'Content-Type': 'application/json'
                }
                
                # URL encode the query
                import urllib.parse
                encoded_query = urllib.parse.quote(query)
                url = f"{self.sf.base_url}tooling/query/?q={encoded_query}"
                
                response = requests.get(url, headers=headers, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    results.extend(data.get('records', []))
                    
                    # Handle pagination
                    while not data.get('done', True):
                        next_url = f"{self.sf.base_url}{data['nextRecordsUrl']}"
                        response = requests.get(next_url, headers=headers, timeout=30)
                        if response.status_code == 200:
                            data = response.json()
                            results.extend(data.get('records', []))
                        else:
                            break
                else:
                    logger.error(f"Tooling API query failed with status {response.status_code}: {response.text}")
            else:
                # Use standard API
                query_result = self.sf.query(query)
                results.extend(query_result['records'])
                
                # Handle pagination
                while not query_result['done']:
                    query_result = self.sf.query_more(
                        query_result['nextRecordsUrl'],
                        identifier_is_url=True
                    )
                    results.extend(query_result['records'])
        
        except Exception as e:
            logger.error(f"Query failed: {str(e)}")
            logger.error(f"Query: {query}")
        
        return results
    
    def _filter_by_exclusions(self, records: List[Dict]) -> List[Dict]:
        """Filter records based on exclusion patterns"""
        if not self.config.get('audit', {}).get('exclusions', {}).get('exclude_patterns'):
            return records
        
        patterns = self.config['audit']['exclusions'].get('exclude_patterns', [])
        
        filtered = []
        for record in records:
            name = record.get('Name', '')
            
            # Check exclusion patterns
            excluded = False
            for pattern in patterns:
                import re
                if re.match(pattern, name):
                    excluded = True
                    break
            
            if not excluded:
                filtered.append(record)
        
        return filtered


class StaticAnalysisRunner:
    """Runs static analysis tools (PMD, SFDX Scanner)"""
    
    def __init__(self, config: Dict):
        """
        Initialize static analysis runner
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.enabled = config.get('audit', {}).get('static_analysis', {}).get('enabled', True)
    
    def run_pmd_analysis(self, source_dir: str) -> List[Dict]:
        """
        Run PMD analysis on source code
        
        Args:
            source_dir: Directory containing source code
        
        Returns:
            List of violations found
        """
        if not self.enabled:
            logger.info("Static analysis disabled")
            return []
        
        logger.info("Running PMD analysis...")
        
        pmd_path = self.config.get('audit', {}).get('static_analysis', {}).get('pmd_path')
        
        if not pmd_path:
            logger.warning("PMD path not configured - skipping PMD analysis")
            return []
        
        # PMD command would be executed here
        # This is a placeholder for actual implementation
        logger.warning("PMD analysis not yet fully implemented")
        
        return []
    
    def run_sfdx_scanner(self, source_dir: str) -> List[Dict]:
        """
        Run SFDX Code Scanner
        
        Args:
            source_dir: Directory containing source code
        
        Returns:
            List of violations found
        """
        if not self.enabled:
            return []
        
        logger.info("Running SFDX Scanner...")
        
        try:
            result = subprocess.run(
                ['sfdx', 'scanner:run', '--target', source_dir, '--format', 'json'],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                violations = json.loads(result.stdout)
                logger.info(f"SFDX Scanner found {len(violations)} violations")
                return violations
            else:
                logger.error(f"SFDX Scanner failed: {result.stderr}")
                return []
                
        except FileNotFoundError:
            logger.warning("SFDX Scanner not found - skipping")
            return []
        except subprocess.TimeoutExpired:
            logger.error("SFDX Scanner timed out")
            return []
        except Exception as e:
            logger.error(f"SFDX Scanner error: {str(e)}")
            return []


if __name__ == "__main__":
    print("Salesforce Utilities Module - Use via main audit script")

