"""
Pattern Matcher Module for Salesforce Code Audit
Implements intelligent detection of SOQL/DML in loops with comprehensive false-positive prevention
"""

import re
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Enum


class ViolationType(Enum):
    """Types of governor limit violations"""
    SOQL_IN_LOOP = "SOQL in Loop"
    DML_IN_LOOP = "DML in Loop"
    INDIRECT_SOQL = "Indirect SOQL in Loop"
    INDIRECT_DML = "Indirect DML in Loop"
    NON_RESTRICTIVE_QUERY = "Non-Restrictive Query"
    FUTURE_METHOD = "@future Method Usage"
    ASYNC_IN_TRIGGER = "Async in Trigger"
    EVENTBUS_NO_CALLBACK = "EventBus without Callback"
    CMDT_SOQL = "CMDT SOQL without Filter"
    HARDCODED_ID = "Hardcoded Salesforce ID"
    # Security Violations
    CRUD_FLS_VIOLATION = "Missing CRUD/FLS Check"
    SOQL_INJECTION = "SOQL Injection Risk"
    MISSING_SHARING = "Missing Sharing Keyword"
    HARDCODED_CREDENTIALS = "Hardcoded Credentials"
    # Code Quality
    GENERIC_EXCEPTION = "Generic Exception Catch"
    SYSTEM_DEBUG_SENSITIVE = "System.debug with Sensitive Data"
    RECURSIVE_TRIGGER = "Recursive Trigger Risk"
    NESTED_LOOPS = "Nested Loops with DML/SOQL"
    # Test Issues
    MISSING_ASSERTIONS = "Missing Test Assertions"
    SEE_ALL_DATA = "@isTest(SeeAllData=true)"
    MISSING_PERSONA_TESTING = "Missing Persona-Based Testing"
    MIXED_DML = "Mixed DML Operations"
    SCHEMA_GLOBAL_DESCRIBE_IN_LOOP = "Schema.getGlobalDescribe() in Loop"
    SCHEMA_GLOBAL_DESCRIBE_NOT_EFFICIENT = "Schema.getGlobalDescribe() Not Efficient"
    REDUNDANT_SOQL = "Redundant SOQL"
    SOBJECT_MAP_IN_FOR_LOOP = "SObject Map in a For Loop"
    SOQL_WITH_NEGATIVE_EXPRESSIONS = "SOQL with Negative Expressions"
    SOQL_WITH_UNUSED_FIELDS = "SOQL with Unused Fields"
    SOQL_WITH_WILDCARD_FILTER = "SOQL with Wildcard Filter"
    SOQL_WITHOUT_WHERE_OR_LIMIT = "SOQL Without a WHERE Clause or LIMIT Statement"
    UNUSED_METHODS = "Unused Methods"
    SOQL_WITH_APEX_FILTER = "SOQL with Apex Filter"
    EXPENSIVE_METHODS_IN_LOOP = "Expensive Methods in Loop"
    EXPENSIVE_STRING_COMPARISON = "Expensive String Comparison"
    COPYING_ELEMENTS_WITH_FOR_LOOP = "Copying Elements with for Loop"
    SORTING_IN_APEX = "Sorting in Apex Instead of SOQL ORDER BY"
    BUSY_LOOP_DELAY = "Busy Loop Delay"
    LIMITS_GET_HEAP_SIZE_IN_LOOP = "Limits.getHeapSize() in Loop"


@dataclass
class Violation:
    """Represents a code violation"""
    violation_type: ViolationType
    file_name: str
    line_number: int
    code_snippet: str
    is_direct: bool = True
    call_chain: Optional[List[str]] = None
    recommendation: str = ""
    criticality: str = "High"


class CodePreprocessor:
    """Preprocesses code to remove comments and prepare for analysis"""
    
    @staticmethod
    def remove_block_comments(code: str) -> str:
        """
        Remove block comments but preserve line numbers by replacing with blank lines
        """
        def replacer(match):
            # Count newlines in the comment and replace with same number of newlines
            comment_text = match.group(0)
            newline_count = comment_text.count('\n')
            return '\n' * newline_count
        
        # Replace multi-line block comments with equivalent blank lines
        code = re.sub(r'/\*.*?\*/', replacer, code, flags=re.DOTALL)
        return code
    
    @staticmethod
    def is_single_line_comment(line: str) -> bool:
        """Check if a line is a single-line comment"""
        stripped = line.strip()
        return stripped.startswith('//')
    
    @staticmethod
    def preprocess_code(code: str) -> List[str]:
        """
        Preprocess code: replace block comments with blank lines to preserve line numbers
        Returns list of lines with line numbers preserved
        """
        # Replace block comments with blank lines (preserves line numbers)
        code_without_blocks = CodePreprocessor.remove_block_comments(code)
        
        # Split into lines
        lines = code_without_blocks.split('\n')
        
        return lines


class LoopDetector:
    """Detects loops in Apex code"""
    
    # Loop patterns
    FOR_LOOP_PATTERN = re.compile(r'^\s*for\s*\(', re.IGNORECASE)
    WHILE_LOOP_PATTERN = re.compile(r'^\s*while\s*\(', re.IGNORECASE)
    DO_WHILE_PATTERN = re.compile(r'^\s*do\s*\{', re.IGNORECASE)
    
    # SOQL-for loop pattern (allowed pattern)
    SOQL_FOR_PATTERN = re.compile(
        r'^\s*for\s*\([^:]+:\s*\[SELECT\s+',
        re.IGNORECASE
    )
    
    @staticmethod
    def is_loop_start(line: str) -> bool:
        """Check if line starts a loop"""
        return bool(
            LoopDetector.FOR_LOOP_PATTERN.match(line) or
            LoopDetector.WHILE_LOOP_PATTERN.match(line) or
            LoopDetector.DO_WHILE_PATTERN.match(line)
        )
    
    @staticmethod
    def is_soql_for_loop(line: str) -> bool:
        """Check if line is a SOQL-for loop (allowed pattern)"""
        return bool(LoopDetector.SOQL_FOR_PATTERN.match(line))
    
    @staticmethod
    def find_loops(lines: List[str]) -> List[Tuple[int, int]]:
        """
        Find all loop blocks in code.
        Returns list of (start_line, end_line) tuples.
        Properly handles both braced and braceless loop bodies.
        For braceless loops (e.g. `for(...) stmt;`), only the next
        statement is treated as the body — not everything up to
        the next unrelated closing brace.
        """
        loops = []
        i = 0

        while i < len(lines):
            if not LoopDetector.is_loop_start(lines[i]):
                i += 1
                continue

            # --- Find where the loop header's closing ')' is ---
            header_end = i
            close_paren_col = -1
            paren_count = 0
            found_open_paren = False

            for k in range(i, len(lines)):
                for col, ch in enumerate(lines[k]):
                    if ch == '(':
                        paren_count += 1
                        found_open_paren = True
                    elif ch == ')':
                        paren_count -= 1
                        if found_open_paren and paren_count == 0:
                            header_end = k
                            close_paren_col = col
                            break
                if close_paren_col >= 0:
                    break

            # --- Determine if the body is braced or braceless ---
            has_brace = False

            if close_paren_col >= 0:
                rest_of_line = lines[header_end][close_paren_col + 1:]
                if '{' in rest_of_line:
                    has_brace = True

            if not has_brace:
                for k in range(header_end + 1, min(header_end + 3, len(lines))):
                    stripped_k = lines[k].strip()
                    if stripped_k:
                        if '{' in stripped_k:
                            has_brace = True
                        break

            if has_brace:
                # Braced loop — find matching '}' via brace counting
                brace_count = 0
                found_open_brace = False
                for k in range(i, len(lines)):
                    for ch in lines[k]:
                        if ch == '{':
                            brace_count += 1
                            found_open_brace = True
                        elif ch == '}':
                            brace_count -= 1
                    if found_open_brace and brace_count <= 0:
                        loops.append((i, k))
                        break
            else:
                # Braceless loop — body is only the next statement (until ';')
                j = header_end + 1
                while j < len(lines):
                    stripped_j = lines[j].strip()
                    if stripped_j and not CodePreprocessor.is_single_line_comment(stripped_j):
                        stmt_end = j
                        while stmt_end < len(lines) and ';' not in lines[stmt_end]:
                            stmt_end += 1
                        loops.append((i, min(stmt_end + 1, len(lines))))
                        break
                    j += 1

            i += 1

        return loops


class DMLDetector:
    """Detects DML statements with intelligent false-positive filtering"""
    
    # DML keywords
    DML_KEYWORDS = ['insert', 'update', 'delete', 'upsert', 'undelete']
    
    # Patterns to exclude (not actual DML)
    VARIABLE_DECLARATION_PATTERN = re.compile(
        r'^\s*(List|Set|Map|Database\.SaveResult|Database\.DeleteResult|'
        r'Database\.UpsertResult|Database\.UndeleteResult)',
        re.IGNORECASE
    )
    
    # Collection method calls (not DML)
    COLLECTION_METHOD_PATTERN = re.compile(
        r'\.(add|put|addAll|remove|clear)\s*\(',
        re.IGNORECASE
    )
    
    # Actual DML statement patterns
    # Allow dotted property access (e.g. wrapper.record) and array indexing
    # (e.g. list[0]) after the DML keyword, not just simple identifiers.
    DML_STATEMENT_PATTERN = re.compile(
        r'^\s*(insert|update|delete|upsert|undelete)\s+[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*|\[\d+\])*\s*;',
        re.IGNORECASE
    )
    
    DATABASE_DML_PATTERN = re.compile(
        r'^\s*Database\.(insert|update|delete|upsert|undelete)\s*\(',
        re.IGNORECASE
    )

    # Same as DATABASE_DML_PATTERN, but matches anywhere on the line so that
    # patterns like `Database.SaveResult x = Database.update(records, false);`
    # are still detected as DML rather than dismissed as a variable declaration.
    DATABASE_DML_PATTERN_ANY = re.compile(
        r'\bDatabase\.(insert|update|delete|upsert|undelete)\s*\(',
        re.IGNORECASE
    )

    # Strip Apex string literals so DML keywords inside strings/log messages
    # do not produce false positives.
    STRING_LITERAL_PATTERN = re.compile(r"'(?:\\.|[^'\\])*'")
    LINE_COMMENT_PATTERN = re.compile(r'//.*$')

    @staticmethod
    def is_dml_statement(line: str) -> bool:
        """
        Check if line contains an actual DML statement
        Returns True only for actual DML, not variable declarations or comments
        """
        stripped = line.strip()

        # Skip comments
        if CodePreprocessor.is_single_line_comment(stripped):
            return False

        # Strip end-of-line comments and string literals so keywords/log text
        # inside them cannot drive detection.
        code_part = DMLDetector.LINE_COMMENT_PATTERN.sub('', stripped)
        code_part = DMLDetector.STRING_LITERAL_PATTERN.sub("''", code_part)

        # Database.<dml>(...) anywhere on the line is unambiguously DML.
        # Detect this BEFORE the variable-declaration filter so that lines like
        # `Database.SaveResult result = Database.update(records, false);`
        # are still counted as DML.
        if DMLDetector.DATABASE_DML_PATTERN_ANY.search(code_part):
            return True

        # Skip variable declarations (only relevant for the bare-keyword form).
        if DMLDetector.VARIABLE_DECLARATION_PATTERN.match(code_part):
            return False

        # Skip collection methods such as list.add() / map.put()
        if DMLDetector.COLLECTION_METHOD_PATTERN.search(code_part):
            return False

        # Skip bare-keyword lines that are actually assignments (e.g. `myVar = update(x);`)
        for keyword in DMLDetector.DML_KEYWORDS:
            keyword_pos = code_part.lower().find(keyword)
            if keyword_pos >= 0 and '=' in code_part[:keyword_pos]:
                return False

        # Bare DML keyword statements: `insert acc;`, `update accs;`, etc.
        if DMLDetector.DML_STATEMENT_PATTERN.match(code_part):
            return True

        return False
    
    @staticmethod
    def extract_dml_keyword(line: str) -> Optional[str]:
        """Extract the DML keyword from a line"""
        for keyword in DMLDetector.DML_KEYWORDS:
            if re.search(r'\b' + keyword + r'\b', line, re.IGNORECASE):
                return keyword
        return None


class SOQLDetector:
    """Detects SOQL queries with intelligent filtering"""
    
    # SOQL pattern
    SOQL_PATTERN = re.compile(r'\[SELECT\s+', re.IGNORECASE)
    DATABASE_QUERY_PATTERN = re.compile(r'\bDatabase\.(query|queryWithBinds|getQueryLocator)\s*\(', re.IGNORECASE)
    INLINE_QUERY_START_PATTERN = re.compile(r'(=\s*\[|\breturn\s+\[|[\(:,]\s*\[|\[\s*SELECT\b)', re.IGNORECASE)
    SELECT_KEYWORD_PATTERN = re.compile(r'\bSELECT\b', re.IGNORECASE)
    
    # Variable assignment pattern
    ASSIGNMENT_PATTERN = re.compile(r'=')
    
    @staticmethod
    def is_soql_query(line: str) -> bool:
        """
        Check if line contains a SOQL query
        Excludes SOQL-for loop headers
        """
        stripped = line.strip()
        
        # Skip comments
        if CodePreprocessor.is_single_line_comment(stripped):
            return False
        
        if SOQLDetector.DATABASE_QUERY_PATTERN.search(stripped):
            return True
        
        # Check for SOQL pattern
        if SOQLDetector.SOQL_PATTERN.search(stripped):
            # Exclude SOQL-for loop (will be checked separately)
            if LoopDetector.is_soql_for_loop(stripped):
                return False
            return True
        
        return False

    @staticmethod
    def _collect_statement(lines: List[str], start_index: int, max_lines: int = 50) -> Tuple[List[str], int]:
        """Collect a statement until the terminating semicolon."""
        statement_lines = []
        paren_depth = 0
        bracket_depth = 0
        upper_bound = min(len(lines), start_index + max_lines)
        end_index = start_index

        for j in range(start_index, upper_bound):
            current = lines[j]
            statement_lines.append(current)
            end_index = j

            if not CodePreprocessor.is_single_line_comment(current):
                paren_depth += current.count('(') - current.count(')')
                bracket_depth += current.count('[') - current.count(']')

            if ';' in current and paren_depth <= 0 and bracket_depth <= 0:
                break

        return statement_lines, end_index

    @staticmethod
    def collect_inline_query(lines: List[str], start_index: int, max_lines: int = 50) -> Optional[Dict]:
        """Collect an inline SOQL query, including bracket-split multiline forms."""
        line = lines[start_index]
        stripped = line.strip()

        if CodePreprocessor.is_single_line_comment(stripped):
            return None

        if LoopDetector.is_soql_for_loop(stripped):
            return None

        if not (
            SOQLDetector.SOQL_PATTERN.search(stripped) or
            SOQLDetector.INLINE_QUERY_START_PATTERN.search(stripped)
        ):
            return None

        query_lines = []
        bracket_depth = 0
        seen_open_bracket = False
        seen_select = False
        upper_bound = min(len(lines), start_index + max_lines)

        for j in range(start_index, upper_bound):
            current = lines[j]
            query_lines.append(current)

            if not CodePreprocessor.is_single_line_comment(current):
                if '[' in current:
                    seen_open_bracket = True
                bracket_depth += current.count('[') - current.count(']')
                if SOQLDetector.SELECT_KEYWORD_PATTERN.search(current):
                    seen_select = True

            if seen_open_bracket and seen_select and bracket_depth <= 0:
                full_query = ' '.join(query_lines)
                if LoopDetector.is_soql_for_loop(full_query.strip()):
                    return None
                return {
                    'start_line': start_index,
                    'end_line': j,
                    'line': line,
                    'full_query': full_query,
                    'query_kind': 'inline',
                }

            if seen_open_bracket and j >= start_index + 8 and not seen_select:
                break

        return None

    @staticmethod
    def collect_dynamic_query(lines: List[str], start_index: int, max_lines: int = 50) -> Optional[Dict]:
        """Collect Database.query-style SOQL execution."""
        line = lines[start_index]
        stripped = line.strip()

        if CodePreprocessor.is_single_line_comment(stripped):
            return None

        if not SOQLDetector.DATABASE_QUERY_PATTERN.search(stripped):
            return None

        statement_lines, end_index = SOQLDetector._collect_statement(lines, start_index, max_lines=max_lines)
        return {
            'start_line': start_index,
            'end_line': end_index,
            'line': line,
            'full_query': ' '.join(statement_lines),
            'query_kind': 'dynamic',
        }

    @staticmethod
    def collect_query_execution(lines: List[str], start_index: int, include_dynamic: bool = False, max_lines: int = 50) -> Optional[Dict]:
        """Collect an inline or dynamic query execution starting on the provided line."""
        inline_query = SOQLDetector.collect_inline_query(lines, start_index, max_lines=max_lines)
        if inline_query:
            return inline_query

        if include_dynamic:
            return SOQLDetector.collect_dynamic_query(lines, start_index, max_lines=max_lines)

        return None
    
    @staticmethod
    def is_non_restrictive_query(line: str) -> bool:
        """Check if SOQL query lacks meaningful WHERE clause"""
        if not SOQLDetector.SOQL_PATTERN.search(line):
            return False
        
        # Extract object name from query (more robust pattern)
        # Pattern: SELECT ... FROM ObjectName (captures full object name including __ suffixes)
        # For queries with subqueries, find the LAST (outermost) FROM clause
        from_matches = list(re.finditer(r'FROM\s+([\w_]+)', line, re.IGNORECASE))
        if from_matches:
            # Use the last FROM match (the main query, not subquery)
            from_match = from_matches[-1]
            object_name = from_match.group(1).strip()
            
            # Check if it ends with __mdt (Custom Metadata Type) - case insensitive
            if object_name.lower().endswith('__mdt'):
                return False
            
            # Check if it ends with __c (could be custom setting) - query the name pattern
            # If it's a Settings pattern, likely a custom setting
            if object_name.lower().endswith('__c') and 'setting' in object_name.lower():
                return False
            
            # Check if it ends with __r (relationship name in subquery) - not the main object
            if object_name.lower().endswith('__r'):
                # This is likely a subquery relationship, skip it
                # Try to find a FROM that doesn't end with __r
                for match in reversed(from_matches):
                    obj = match.group(1).strip()
                    if not obj.lower().endswith('__r'):
                        object_name = obj
                        break
            
            # Exclude metadata objects, custom settings, and custom metadata
            excluded_objects = [
                # Metadata objects
                'ApexClass', 'ApexTrigger', 'ApexPage', 'ApexComponent',
                'CustomObject', 'CustomField', 'FieldDefinition', 'EntityDefinition',
                'Profile', 'PermissionSet', 'PermissionSetAssignment',
                'User', 'Group', 'Organization', 'UserRole',
                'CustomPermission', 'CustomMetadataType', 'CustomSetting',
                'StaticResource', 'Document', 'EmailTemplate',
                'FlowDefinition', 'FlowDefinitionView', 'Flow',
                'LayoutDefinition', 'ValidationRule', 'WorkflowRule',
                'ProcessDefinition', 'ApexCodeCoverage', 'ApexCodeCoverageAggregate',
                'ToolingApiUser', 'MetadataComponent', 'SetupAuditTrail',
                'AsyncApexJob', 'CronTrigger', 'QueueSobject',
                'ContentVersion', 'ContentDocument',  # Content objects
                # Framework/Configuration objects
                'Trigger_Framework__mdt', 'TriggerFramework__mdt',
                # Add more metadata objects as needed
            ]
            
            # Check if it's a metadata object (case-insensitive)
            if any(object_name.lower() == excluded.lower() for excluded in excluded_objects):
                return False
        
        # Check for WHERE clause
        if 'WHERE' not in line.upper():
            return True
        
        # Check for overly broad filters
        broad_filters = [
            r'WHERE\s+Id\s*!=\s*null',
            r'WHERE\s+\d+\s*=\s*\d+',  # WHERE 1=1
            r'WHERE\s+true',
        ]
        
        for pattern in broad_filters:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        
        return False


class GovernorLimitAnalyzer:
    """Main analyzer for governor limit violations"""
    
    def __init__(self, file_name: str, code: str):
        self.file_name = file_name
        self.code = code
        self.violations: List[Violation] = []
        
        # Preprocess code
        self.lines = CodePreprocessor.preprocess_code(code)
        
        # Find loops
        self.loops = LoopDetector.find_loops(self.lines)
        self.class_name = self._extract_primary_class_name()
        self._soql_query_cache: Optional[List[Dict]] = None
        self._soql_execution_cache: Optional[List[Dict]] = None
        self._local_method_cache: Optional[Dict[str, Dict]] = None
        self._local_method_effect_cache: Dict[str, Dict] = {}
    
    def analyze(self) -> List[Violation]:
        """Run all analysis checks"""
        # Governor Limit Checks
        self._check_soql_in_loops()
        self._check_dml_in_loops()
        self._check_indirect_loop_operations()
        self._check_non_restrictive_queries()
        self._check_redundant_soql()
        self._check_future_methods()
        self._check_eventbus_usage()
        self._check_cmdt_access()
        self._check_hardcoded_ids()
        self._check_nested_loops()
        self._check_schema_getglobaldescribe_in_loops()
        self._check_inefficient_global_describe_usage()
        self._check_sobject_map_in_for_loop()
        self._check_soql_with_negative_expressions()
        self._check_soql_with_unused_fields()
        self._check_soql_with_wildcard_filter()
        self._check_soql_with_apex_filter()
        self._check_expensive_methods_in_loops()
        self._check_expensive_string_comparison()
        self._check_copying_elements_with_for_loop()
        self._check_sorting_in_apex()
        self._check_busy_loop_delay()
        self._check_limits_getheapsize_in_loop()
        
        # Security Checks
        self._check_crud_fls()
        self._check_soql_fls_violations()  # New: Check SOQL queries for FLS enforcement
        self._check_soql_injection()
        self._check_missing_sharing()
        self._check_hardcoded_credentials()
        self._check_system_debug_sensitive()
        
        # Code Quality Checks
        self._check_generic_exceptions()
        self._check_recursive_triggers()
        self._check_mixed_dml()
        self._check_unused_methods()
        
        return self.violations
    
    def _check_soql_in_loops(self):
        """Check for SOQL queries inside loop bodies"""
        # Dedupe so a query that sits inside both an outer and inner loop is
        # reported once at its actual line number, not once per containing loop.
        reported_lines: Set[int] = set()
        for start_line, end_line in self.loops:
            for query in self._collect_soql_executions(include_dynamic=True):
                if not (start_line < query['start_line'] <= end_line):
                    continue
                if query['start_line'] in reported_lines:
                    continue
                reported_lines.add(query['start_line'])

                recommendation = "Move SOQL query outside the loop or use a SOQL-for loop"
                if query.get('query_kind') == 'dynamic':
                    recommendation = "Move Database.query()/queryWithBinds()/getQueryLocator() outside the loop or bulkify the helper logic"

                self.violations.append(Violation(
                    violation_type=ViolationType.SOQL_IN_LOOP,
                    file_name=self.file_name,
                    line_number=query['start_line'] + 1,
                    code_snippet=query['line'].strip(),
                    is_direct=True,
                    recommendation=recommendation,
                    criticality="Critical"
                ))

    def _check_dml_in_loops(self):
        """Check for DML statements inside loop bodies"""
        # Dedupe so the same DML line is not reported once per enclosing loop
        # when loops are nested.
        reported_lines: Set[int] = set()
        for start_line, end_line in self.loops:
            for i in range(start_line + 1, end_line):
                if i in reported_lines:
                    continue

                line = self.lines[i]
                if CodePreprocessor.is_single_line_comment(line):
                    continue

                if DMLDetector.is_dml_statement(line):
                    reported_lines.add(i)
                    keyword = DMLDetector.extract_dml_keyword(line)

                    self.violations.append(Violation(
                        violation_type=ViolationType.DML_IN_LOOP,
                        file_name=self.file_name,
                        line_number=i + 1,
                        code_snippet=line.strip(),
                        is_direct=True,
                        recommendation=f"Collect records in a list and perform bulk {keyword} after the loop",
                        criticality="Critical"
                    ))

    def _check_indirect_loop_operations(self):
        """Check for helper methods invoked inside loops that execute SOQL or DML."""
        methods = self._get_local_method_definitions()
        if not methods:
            return

        method_names = list(methods.keys())
        # Track across ALL loops so the same call is not reported once per
        # enclosing loop in nested-loop structures.
        seen: Set[Tuple[int, str, str]] = set()

        for start_line, end_line in self.loops:
            for i in range(start_line + 1, end_line):
                line = self.lines[i]
                if CodePreprocessor.is_single_line_comment(line):
                    continue

                called_methods = self._extract_local_method_calls_from_line(line, method_names)
                for method_name in sorted(called_methods):
                    effects = self._summarize_local_method_effects(method_name)

                    if effects['has_soql']:
                        key = (i, method_name, 'soql')
                        if key not in seen:
                            seen.add(key)
                            self.violations.append(Violation(
                                violation_type=ViolationType.INDIRECT_SOQL,
                                file_name=self.file_name,
                                line_number=i + 1,
                                code_snippet=line.strip(),
                                is_direct=False,
                                call_chain=effects['soql_chain'],
                                recommendation=f"Method '{method_name}' executes SOQL and is called from inside a loop. Query once outside the loop and reuse the results.",
                                criticality="High"
                            ))

                    if effects['has_dml']:
                        key = (i, method_name, 'dml')
                        if key not in seen:
                            seen.add(key)
                            self.violations.append(Violation(
                                violation_type=ViolationType.INDIRECT_DML,
                                file_name=self.file_name,
                                line_number=i + 1,
                                code_snippet=line.strip(),
                                is_direct=False,
                                call_chain=effects['dml_chain'],
                                recommendation=f"Method '{method_name}' performs DML and is called from inside a loop. Collect records first and execute DML once after the loop.",
                                criticality="High"
                            ))
    
    def _check_non_restrictive_queries(self):
        """Check for queries without meaningful WHERE clauses (handles multi-line queries)"""
        for query in self._collect_soql_queries():
            full_query = query['full_query']
            query_upper = full_query.upper()

            if 'WHERE' not in query_upper and 'LIMIT' not in query_upper:
                self.violations.append(Violation(
                    violation_type=ViolationType.SOQL_WITHOUT_WHERE_OR_LIMIT,
                    file_name=self.file_name,
                    line_number=query['start_line'] + 1,
                    code_snippet=query['line'].strip(),
                    recommendation="Add a WHERE clause or LIMIT statement so the query does not scan excessive records.",
                    criticality="High"
                ))
            elif SOQLDetector.is_non_restrictive_query(full_query):
                self.violations.append(Violation(
                    violation_type=ViolationType.NON_RESTRICTIVE_QUERY,
                    file_name=self.file_name,
                    line_number=query['start_line'] + 1,
                    code_snippet=query['line'].strip(),
                    recommendation="Add a meaningful WHERE clause to limit query results",
                    criticality="High"
                ))

    def _collect_soql_executions(self, include_dynamic: bool = True) -> List[Dict]:
        """Collect SOQL executions, optionally including Database.query-style calls."""
        if include_dynamic and self._soql_execution_cache is not None:
            return self._soql_execution_cache

        if not include_dynamic and self._soql_query_cache is not None:
            return self._soql_query_cache

        queries = []
        assignment_pattern = re.compile(
            r'(?:[\w<>,\[\]\s]+\s+)?(\w+)\s*=\s*\[\s*SELECT\b',
            re.IGNORECASE
        )
        i = 0

        while i < len(self.lines):
            line = self.lines[i]
            if CodePreprocessor.is_single_line_comment(line):
                i += 1
                continue

            query = SOQLDetector.collect_query_execution(
                self.lines,
                i,
                include_dynamic=include_dynamic,
                max_lines=50
            )
            if not query:
                i += 1
                continue

            query = dict(query)
            assignment_match = None
            if query.get('query_kind') == 'inline':
                assignment_match = assignment_pattern.search(query['full_query'])

            query['assigned_var'] = assignment_match.group(1) if assignment_match else None
            query['is_collection'] = 'List<' in query['full_query'] or 'Set<' in query['full_query']
            queries.append(query)
            i = query['end_line'] + 1

        if include_dynamic:
            self._soql_execution_cache = queries
        else:
            self._soql_query_cache = queries

        return queries

    def _collect_soql_queries(self) -> List[Dict]:
        """Collect inline SOQL queries with basic metadata for downstream checks"""
        return self._collect_soql_executions(include_dynamic=False)

    def _extract_simple_select_fields(self, full_query: str) -> List[str]:
        """Extract simple top-level SELECT fields for high-confidence field-usage checks"""
        match = re.search(r'\bSELECT\s+(.*?)\s+FROM\b', full_query, re.IGNORECASE | re.DOTALL)
        if not match:
            return []

        field_clause = match.group(1).strip()
        if not field_clause or 'SELECT ' in field_clause.upper() or '(' in field_clause or ')' in field_clause:
            return []

        raw_fields = [field.strip() for field in field_clause.split(',')]
        fields = []
        for field in raw_fields:
            if not re.fullmatch(r'[A-Za-z_]\w*(?:__c)?', field):
                return []
            if field.lower() != 'id':
                fields.append(field)
        return fields

    def _find_enclosing_method_end(self, line_index: int) -> int:
        """Find the end line of the method that contains the provided line"""
        method_pattern = re.compile(
            r'^\s*(?:public|private|protected|global)?\s*(?:static\s+)?(?:virtual\s+|override\s+|testMethod\s+)?[\w<>,\[\]\s]+\s+\w+\s*\([^;]*\)\s*\{',
            re.IGNORECASE
        )
        control_keywords = ('if', 'for', 'while', 'switch', 'catch')

        method_start = None
        for i in range(line_index, -1, -1):
            stripped = self.lines[i].strip()
            lowered = stripped.lower()
            if any(lowered.startswith(keyword + ' ') or lowered.startswith(keyword + '(') for keyword in control_keywords):
                continue
            if method_pattern.match(stripped):
                method_start = i
                break

        if method_start is None:
            return min(len(self.lines) - 1, line_index + 80)

        brace_depth = 0
        seen_open = False
        for i in range(method_start, len(self.lines)):
            current = re.sub(r'//.*', '', self.lines[i])
            brace_depth += current.count('{')
            if '{' in current:
                seen_open = True
            brace_depth -= current.count('}')
            if seen_open and brace_depth <= 0:
                return i
        return len(self.lines) - 1

    def _extract_primary_class_name(self) -> Optional[str]:
        """Extract the main class name from the file when present."""
        class_pattern = re.compile(r'\bclass\s+(\w+)', re.IGNORECASE)
        for line in self.lines:
            if CodePreprocessor.is_single_line_comment(line):
                continue
            match = class_pattern.search(line)
            if match:
                return match.group(1)
        return None

    def _find_method_end_from_start(self, start_index: int) -> int:
        """Find the closing brace for a method declaration line."""
        brace_depth = 0
        seen_open = False

        for i in range(start_index, len(self.lines)):
            current = re.sub(r'//.*', '', self.lines[i])
            brace_depth += current.count('{')
            if '{' in current:
                seen_open = True
            brace_depth -= current.count('}')
            if seen_open and brace_depth <= 0:
                return i

        return len(self.lines) - 1

    def _extract_local_method_calls_from_line(self, line: str, method_names: List[str]) -> Set[str]:
        """Extract direct calls to methods defined in the same class."""
        stripped = line.strip()
        calls: Set[str] = set()

        for method_name in method_names:
            direct_pattern = re.compile(rf'(?<!\.)\b{re.escape(method_name)}\s*\(', re.IGNORECASE)
            if direct_pattern.search(stripped):
                calls.add(method_name)
                continue

            if self.class_name:
                receiver_pattern = re.compile(
                    rf'\b(?:this|{re.escape(self.class_name)})\s*\.\s*{re.escape(method_name)}\s*\(',
                    re.IGNORECASE
                )
                if receiver_pattern.search(stripped):
                    calls.add(method_name)

        return calls

    def _get_local_method_definitions(self) -> Dict[str, Dict]:
        """Build a map of local method definitions with direct SOQL/DML usage and call graph."""
        if self._local_method_cache is not None:
            return self._local_method_cache

        method_pattern = re.compile(
            r'^\s*(?:@\w+(?:\([^)]*\))?\s*)*(?:public|private|protected|global)?\s*(?:static\s+)?(?:virtual\s+|override\s+|abstract\s+|final\s+|testMethod\s+)?[\w<>,\[\]\s]+\s+(\w+)\s*\([^;]*\)\s*\{',
            re.IGNORECASE
        )
        control_keywords = ('if', 'for', 'while', 'switch', 'catch')
        methods: Dict[str, Dict] = {}
        i = 0

        while i < len(self.lines):
            line = self.lines[i]
            stripped = line.strip()
            lowered = stripped.lower()

            if CodePreprocessor.is_single_line_comment(line):
                i += 1
                continue

            if any(lowered.startswith(keyword + ' ') or lowered.startswith(keyword + '(') for keyword in control_keywords):
                i += 1
                continue

            match = method_pattern.match(stripped)
            if not match:
                i += 1
                continue

            method_name = match.group(1)
            end_line = self._find_method_end_from_start(i)
            methods[method_name] = {
                'name': method_name,
                'start_line': i,
                'end_line': end_line,
                'calls': set(),
                'has_direct_soql': False,
                'has_direct_dml': False,
            }
            i = end_line + 1

        if not methods:
            self._local_method_cache = methods
            return methods

        soql_executions = self._collect_soql_executions(include_dynamic=True)

        for method in methods.values():
            body_start = method['start_line'] + 1
            body_end = method['end_line']
            method['has_direct_soql'] = any(body_start <= query['start_line'] <= body_end for query in soql_executions)

            for line_index in range(body_start, body_end + 1):
                line = self.lines[line_index]
                if CodePreprocessor.is_single_line_comment(line):
                    continue
                if DMLDetector.is_dml_statement(line):
                    method['has_direct_dml'] = True
                    break

        method_names = list(methods.keys())
        for method in methods.values():
            calls = set()
            for line_index in range(method['start_line'] + 1, method['end_line'] + 1):
                line = self.lines[line_index]
                if CodePreprocessor.is_single_line_comment(line):
                    continue
                calls.update(self._extract_local_method_calls_from_line(line, method_names))
            method['calls'] = calls

        self._local_method_cache = methods
        return methods

    def _resolve_local_method_effects(self, method_name: str, active: Set[str]) -> Dict:
        """Resolve transitive SOQL/DML usage for a local helper method."""
        methods = self._get_local_method_definitions()
        method = methods.get(method_name)
        if not method:
            return {'has_soql': False, 'has_dml': False, 'soql_chain': [], 'dml_chain': []}

        if method_name in active:
            return {
                'has_soql': method['has_direct_soql'],
                'has_dml': method['has_direct_dml'],
                'soql_chain': [method_name] if method['has_direct_soql'] else [],
                'dml_chain': [method_name] if method['has_direct_dml'] else [],
            }

        next_active = set(active)
        next_active.add(method_name)
        summary = {
            'has_soql': method['has_direct_soql'],
            'has_dml': method['has_direct_dml'],
            'soql_chain': [method_name] if method['has_direct_soql'] else [],
            'dml_chain': [method_name] if method['has_direct_dml'] else [],
        }

        for called_method in sorted(method['calls']):
            child = self._resolve_local_method_effects(called_method, next_active)
            if child['has_soql'] and not summary['has_soql']:
                summary['has_soql'] = True
                summary['soql_chain'] = [method_name] + child['soql_chain']
            if child['has_dml'] and not summary['has_dml']:
                summary['has_dml'] = True
                summary['dml_chain'] = [method_name] + child['dml_chain']

            if summary['has_soql'] and summary['has_dml']:
                break

        return summary

    def _summarize_local_method_effects(self, method_name: str) -> Dict:
        """Return cached transitive SOQL/DML effects for a local helper method."""
        if method_name not in self._local_method_effect_cache:
            self._local_method_effect_cache[method_name] = self._resolve_local_method_effects(method_name, set())
        return self._local_method_effect_cache[method_name]
    
    def _check_future_methods(self):
        """Check for @future method usage"""
        future_pattern = re.compile(r'@future', re.IGNORECASE)
        
        for i, line in enumerate(self.lines):
            # Skip single-line comments but keep line numbers accurate
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            if future_pattern.search(line):
                self.violations.append(Violation(
                    violation_type=ViolationType.FUTURE_METHOD,
                    file_name=self.file_name,
                    line_number=i + 1,  # Use original line number (1-indexed)
                    code_snippet=line.strip(),
                    recommendation="Consider using Queueable interface or Platform Events instead of @future for better flexibility and monitoring",
                    criticality="High"
                ))
    
    def _check_eventbus_usage(self):
        """
        Check for EventBus.publish without callback
        Improved logic: Checks if EventBus.publish() has 2 parameters (second = callback)
        """
        eventbus_pattern = re.compile(r'EventBus\.publish\s*\(', re.IGNORECASE)
        
        # Check for EventBus.publish
        for i, line in enumerate(self.lines):
            # Skip single-line comments but keep line numbers accurate
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            match = eventbus_pattern.search(line)
            if match:
                # Extract the part after "EventBus.publish("
                start_pos = match.end()
                publish_call = line[start_pos:]
                
                # Look for second parameter (callback)
                # Strategy 1: Check if there's a comma indicating 2 parameters
                has_callback = False
                
                # Count commas at depth 0 (not inside nested parentheses/brackets)
                paren_depth = 0
                bracket_depth = 0
                comma_count = 0
                
                for char in publish_call:
                    if char == '(':
                        paren_depth += 1
                    elif char == ')':
                        if paren_depth == 0:
                            break  # End of EventBus.publish call
                        paren_depth -= 1
                    elif char == '[':
                        bracket_depth += 1
                    elif char == ']':
                        bracket_depth -= 1
                    elif char == ',' and paren_depth == 0 and bracket_depth == 0:
                        comma_count += 1
                
                # If there's at least 1 comma at depth 0, there's a second parameter (callback)
                if comma_count >= 1:
                    has_callback = True
                
                # Strategy 2: Also check for callback in surrounding lines (legacy check)
                # This catches cases where callback class implements EventBus.EventPublishCallback
                if not has_callback:
                    callback_interface_pattern = re.compile(r'EventBus\.EventPublishCallback', re.IGNORECASE)
                    search_range = range(max(0, i - 10), min(len(self.lines), i + 10))
                    for j in search_range:
                        if callback_interface_pattern.search(self.lines[j]):
                            has_callback = True
                            break
                
                if not has_callback:
                    self.violations.append(Violation(
                        violation_type=ViolationType.EVENTBUS_NO_CALLBACK,
                        file_name=self.file_name,
                        line_number=i + 1,  # Use original line number (1-indexed)
                        code_snippet=line.strip(),
                        recommendation="Implement EventBus.EventPublishCallback to handle publish failures. Use: EventBus.publish(event, callback)",
                        criticality="High"
                    ))
    
    def _check_cmdt_access(self):
        """Check for inefficient Custom Metadata access"""
        cmdt_soql_pattern = re.compile(r'\[SELECT.*FROM\s+\w+__mdt', re.IGNORECASE)
        where_pattern = re.compile(r'WHERE', re.IGNORECASE)
        
        for i, line in enumerate(self.lines):
            # Skip single-line comments but keep line numbers accurate
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            if cmdt_soql_pattern.search(line):
                # Check if query has WHERE clause
                if not where_pattern.search(line):
                    self.violations.append(Violation(
                        violation_type=ViolationType.CMDT_SOQL,
                        file_name=self.file_name,
                        line_number=i + 1,  # Use original line number (1-indexed)
                        code_snippet=line.strip(),
                        recommendation="Use CustomMetadataType.getAll() or getInstance() instead of SOQL without WHERE",
                        criticality="Medium"
                    ))
    
    def _check_hardcoded_ids(self):
        """Check for hardcoded Salesforce IDs (15 or 18 character IDs)"""
        # Pattern to match Salesforce IDs: 15 or 18 alphanumeric characters starting with [a-zA-Z0-9]
        # Common formats: '001xxx...', '003xxx...', '006xxx...', etc.
        # Matches both 15-char and 18-char IDs in strings
        id_pattern = re.compile(r'[\'"]([a-zA-Z0-9]{15}|[a-zA-Z0-9]{18})[\'"]')
        
        # Common Salesforce ID prefixes (first 3 characters indicate object type)
        # 001=Account, 003=Contact, 005=User, 006=Opportunity, 00Q=Lead, etc.
        common_prefixes = ['001', '003', '005', '006', '00Q', '00D', '00G', '00e', '00E', 
                          '012', '015', '701', '500', '801', 'a00', 'a01', 'a02']
        
        for i, line in enumerate(self.lines):
            # Skip single-line comments but keep line numbers accurate
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            # Find all potential IDs in the line
            matches = id_pattern.finditer(line)
            
            for match in matches:
                id_value = match.group(1)
                
                # Check if it starts with a common Salesforce ID prefix
                # and follows Salesforce ID patterns (alphanumeric, case-sensitive)
                if any(id_value.startswith(prefix) for prefix in common_prefixes):
                    # Additional validation: Salesforce IDs are alphanumeric and case-sensitive
                    # Skip if it looks like a test ID or placeholder
                    if 'test' not in id_value.lower() and 'xxxx' not in id_value.lower():
                        self.violations.append(Violation(
                            violation_type=ViolationType.HARDCODED_ID,
                            file_name=self.file_name,
                            line_number=i + 1,  # Use original line number (1-indexed)
                            code_snippet=line.strip(),
                            recommendation="Replace hardcoded ID with dynamic query or Custom Metadata/Label. Hardcoded IDs break across sandboxes and production.",
                            criticality="Critical"
                        ))
                        break  # Only report once per line
    
    def _determine_crud_fls_severity(self, operation, line_context):
        """
        Determine severity of CRUD/FLS violation based on context
        
        🔴 Critical: DML on sensitive operations, triggers, public endpoints
        🟠 High: Internal code, non-critical operations
        🟡 Medium: Utility functions, admin-only code, metadata objects
        """
        code_lower = self.code.lower()
        file_name_lower = self.file_name.lower()
        
        # 🔴 CRITICAL SEVERITY CONDITIONS
        
        # 1. DML operations (INSERT/UPDATE/DELETE/UPSERT) - Direct data modification
        if operation.lower() in ['insert', 'update', 'delete', 'upsert', 
                                  'database.insert', 'database.update', 
                                  'database.delete', 'database.upsert']:
            
            # Triggers always critical (system-mode execution)
            if '.trigger' in file_name_lower or 'trigger' in code_lower[:200]:
                return "Critical", "DML in trigger (system mode) without CRUD/FLS check"
            
            # Public/global endpoints
            if any(keyword in code_lower for keyword in ['@restresource', '@auraenabled', 
                                                          'global class', 'webservice']):
                return "Critical", "DML in public/global endpoint without CRUD/FLS check"
            
            # Schedulable/Batchable/Queueable (system mode)
            if any(keyword in code_lower for keyword in ['implements schedulable', 
                                                          'implements database.batchable',
                                                          'implements queueable']):
                return "Critical", "DML in system-mode class without CRUD/FLS check"
            
            # LWC controllers (@AuraEnabled methods)
            if 'controller' in file_name_lower and '@auraenabled' in code_lower:
                return "Critical", "DML in LWC/Aura controller without CRUD/FLS check"
            
            # Default for DML operations: Critical
            return "Critical", "DML operation without CRUD/FLS check"
        
        # 🟠 HIGH SEVERITY CONDITIONS
        
        # Internal utility classes with non-critical operations
        if any(name in file_name_lower for name in ['util', 'helper', 'service', 'manager']):
            # Check if it's admin-only or internal
            if 'admin' in file_name_lower or 'internal' in file_name_lower:
                return "Medium", "Internal utility code - review for business impact"
            return "High", "Utility/service class without CRUD/FLS check"
        
        # 🟡 MEDIUM SEVERITY CONDITIONS
        
        # Test helper classes (but not actual @isTest classes, those are skipped)
        if 'testutil' in file_name_lower or 'testhelper' in file_name_lower or 'testdata' in file_name_lower:
            return "Medium", "Test helper utility - low risk"
        
        # Metadata-related operations
        if any(obj in line_context.lower() for obj in ['__mdt', 'metadata', 'customsetting']):
            return "Medium", "Metadata/settings operation - limited records"
        
        # Default: High (better to be cautious)
        return "High", "Missing CRUD/FLS check"
    
    def _check_crud_fls(self):
        """Enhanced CRUD/FLS check with all 4 modern security approaches and context-aware severity"""
        # DML patterns including Database methods
        dml_patterns = [
            # Standard DML
            (re.compile(r'\binsert\s+(?!new\s*\()', re.IGNORECASE), 'isCreateable', 'insert', 'CREATABLE'),
            (re.compile(r'\bupdate\s+', re.IGNORECASE), 'isUpdateable', 'update', 'UPDATABLE'),
            (re.compile(r'\bdelete\s+', re.IGNORECASE), 'isDeletable', 'delete', 'DELETABLE'),
            (re.compile(r'\bupsert\s+', re.IGNORECASE), 'isCreateable/isUpdateable', 'upsert', 'CREATABLE'),
            # Database methods
            (re.compile(r'Database\.insert\s*\(', re.IGNORECASE), 'isCreateable', 'Database.insert', 'CREATABLE'),
            (re.compile(r'Database\.update\s*\(', re.IGNORECASE), 'isUpdateable', 'Database.update', 'UPDATABLE'),
            (re.compile(r'Database\.delete\s*\(', re.IGNORECASE), 'isDeletable', 'Database.delete', 'DELETABLE'),
            (re.compile(r'Database\.upsert\s*\(', re.IGNORECASE), 'isCreateable/isUpdateable', 'Database.upsert', 'CREATABLE'),
        ]
        
        # Framework methods to skip (whitelist)
        framework_patterns = [
            'CRUDHelper.', 'SecurityUtil.', 'PermissionManager.',
            'fflib_', 'TriggerHandler.', 'SecurityService.'
        ]
        
        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            # Skip if it's a framework method call
            if any(fw in line for fw in framework_patterns):
                continue
            
            for pattern, permission, operation, access_type in dml_patterns:
                if pattern.search(line):
                    # Check for permission validation (increased to 20 lines before)
                    has_check = False
                    check_method = None
                    search_range = range(max(0, i - 20), i)
                    
                    for j in search_range:
                        check_line = self.lines[j]
                        
                        # Check for ALL 4 modern security approaches:
                        # 1. Security.stripInaccessible (Spring '19+) - BEST for DML
                        if 'Security.stripInaccessible' in check_line:
                            has_check = True
                            check_method = 'Security.stripInaccessible()'
                            break
                        
                        # 2. WITH USER_MODE (Winter '23+) - BEST for SOQL (if checking query-related DML)
                        if 'WITH USER_MODE' in check_line.upper():
                            has_check = True
                            check_method = 'WITH USER_MODE'
                            break
                        
                        # 3. WITH SECURITY_ENFORCED - Legacy SOQL
                        if 'WITH SECURITY_ENFORCED' in check_line.upper():
                            has_check = True
                            check_method = 'WITH SECURITY_ENFORCED'
                            break
                        
                        # 4. Schema.sObjectType checks (Legacy manual approach)
                        if (permission in check_line or 
                            'Schema.sObjectType' in check_line or
                            '.getDescribe()' in check_line or
                            'DescribeSObjectResult' in check_line):
                            has_check = True
                            check_method = 'Schema.sObjectType'
                            break
                    
                    if not has_check:
                        # Skip test classes
                        if '@istest' not in self.code.lower():
                            # Determine severity based on context
                            severity, reason = self._determine_crud_fls_severity(operation, line)
                            
                            self.violations.append(Violation(
                                violation_type=ViolationType.CRUD_FLS_VIOLATION,
                                file_name=self.file_name,
                                line_number=i + 1,
                                code_snippet=line.strip(),
                                recommendation=f"""Add CRUD/FLS enforcement before {operation}. Choose the best approach:

⭐ RECOMMENDED (Modern - Spring '19+):
  SObjectAccessDecision decision = Security.stripInaccessible(
      AccessType.{access_type},
      records
  );
  {operation} decision.getRecords();

Alternative (Legacy - Manual checks):
  if(Schema.sObjectType.ObjectName.{permission}()) {{
      {operation} records;
  }}

For queries, use WITH USER_MODE:
  [SELECT Id, Name FROM Object WITH USER_MODE]

Severity Reason: {reason}

Learn more: https://developer.salesforce.com/docs/atlas.en-us.apexcode.meta/apexcode/apex_classes_perms_enforcing.htm""",
                                criticality=severity
                            ))
                            break
    
    def _determine_soql_fls_severity(self, query_text):
        """
        Determine severity of SOQL FLS violation based on context
        
        🔴 Critical: Queries with sensitive field patterns in public endpoints
        🟠 High: Standard queries without FLS in user-facing code
        🟡 Medium: Metadata queries, utility functions, internal admin code
        """
        code_lower = self.code.lower()
        file_name_lower = self.file_name.lower()
        query_lower = query_text.lower()
        
        # Sensitive field patterns
        sensitive_patterns = [
            'ssn', 'social_security', 'tax_id', 'taxid', 
            'password', 'creditcard', 'credit_card', 'cvv', 
            'account_number', 'accountnumber', 'routing',
            'salary', 'compensation', 'income',
            'dob', 'date_of_birth', 'dateofbirth',
            'driver_license', 'passport'
        ]
        
        # 🔴 CRITICAL SEVERITY CONDITIONS
        
        # 1. Sensitive fields in query
        if any(pattern in query_lower for pattern in sensitive_patterns):
            return "Critical", "Query accessing sensitive fields without FLS enforcement"
        
        # 2. Public/global endpoints
        if any(keyword in code_lower for keyword in ['@restresource', '@auraenabled', 
                                                      'global class', 'webservice']):
            return "Critical", "SOQL in public/global endpoint without FLS enforcement"
        
        # 3. LWC/Aura controllers
        if 'controller' in file_name_lower and '@auraenabled' in code_lower:
            return "Critical", "SOQL in LWC/Aura controller without FLS enforcement"
        
        # 🟡 MEDIUM SEVERITY CONDITIONS
        
        # 1. Metadata queries
        if any(obj in query_lower for obj in ['__mdt', 'metadata', 'customsetting']):
            return "Medium", "Metadata/settings query - limited records, low risk"
        
        # 2. System objects with limited data exposure
        system_objects = ['user', 'profile', 'permissionset', 'group', 'organization']
        if any(f' from {obj} ' in query_lower or f' from {obj}]' in query_lower 
               for obj in system_objects):
            return "Medium", "System object query - review for context"
        
        # 3. Test helpers and utilities
        if any(name in file_name_lower for name in ['testutil', 'testhelper', 'testdata']):
            return "Medium", "Test helper utility - low risk"
        
        # 4. Internal admin-only code
        if 'admin' in file_name_lower or 'internal' in file_name_lower:
            return "Medium", "Internal admin code - review business requirements"
        
        # 🟠 HIGH SEVERITY (Default for most queries)
        
        # Triggers always high (can expose unauthorized data)
        if '.trigger' in file_name_lower or 'trigger' in code_lower[:200]:
            return "High", "SOQL in trigger without FLS - unauthorized data exposure risk"
        
        # Services and handlers
        if any(name in file_name_lower for name in ['service', 'handler', 'manager', 'processor']):
            return "High", "SOQL in service/handler without FLS enforcement"
        
        # Default: High (unauthorized data read)
        return "High", "SOQL query without FLS enforcement - unauthorized data exposure risk"
    
    def _check_soql_fls_violations(self):
        """Check for SOQL queries without FLS enforcement with context-aware severity"""
        
        soql_pattern = re.compile(r'\[SELECT\s+', re.IGNORECASE)
        
        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            if soql_pattern.search(line):
                # Look ahead to see if query has WITH USER_MODE or WITH SECURITY_ENFORCED
                has_security = False
                
                # Check current line and next 20 lines for multi-line queries
                check_range = range(i, min(len(self.lines), i + 20))
                query_text = ''
                
                for j in check_range:
                    query_text += ' ' + self.lines[j].upper()
                    if ']' in self.lines[j]:  # End of query
                        break
                
                # Check for security clauses in the query
                if 'WITH USER_MODE' in query_text or 'WITH SECURITY_ENFORCED' in query_text:
                    has_security = True
                
                # Also check if there's a stripInaccessible call after the query (within 5 lines)
                if not has_security:
                    after_range = range(i + 1, min(len(self.lines), i + 6))
                    for j in after_range:
                        if 'Security.stripInaccessible' in self.lines[j]:
                            has_security = True
                            break
                
                # Also check for Schema checks before the query (within 10 lines)
                if not has_security:
                    before_range = range(max(0, i - 10), i)
                    for j in before_range:
                        if 'isAccessible' in self.lines[j] or 'Schema.sObjectType' in self.lines[j]:
                            has_security = True
                            break
                
                if not has_security:
                    # Skip test classes
                    if '@istest' not in self.code.lower():
                        # Determine severity based on context
                        severity, reason = self._determine_soql_fls_severity(query_text)
                        
                        recommendation_text = f"""Add FLS enforcement to SOQL query. Choose the best approach:

⭐ RECOMMENDED (Winter '23+ - Most comprehensive):
  [SELECT Id, Name FROM Account WITH USER_MODE]
  // Enforces object CRUD + field FLS + sharing rules

Alternative (Legacy - FLS only):
  [SELECT Id, Name FROM Account WITH SECURITY_ENFORCED]
  // Enforces field-level security only

Or use stripInaccessible after query:
  List<Account> accounts = [SELECT Id, Name FROM Account];
  SObjectAccessDecision decision = Security.stripInaccessible(
      AccessType.READABLE,
      accounts
  );
  return decision.getRecords();

Or manual Schema checks before query:
  if(Schema.sObjectType.Account.isAccessible() &&
     Schema.sObjectType.Account.fields.Name.isAccessible()) {{
      [SELECT Id, Name FROM Account]
  }}

Severity Reason: {reason}

Learn more: https://developer.salesforce.com/docs/atlas.en-us.apexcode.meta/apexcode/apex_classes_perms_enforcing.htm"""
                        
                        self.violations.append(Violation(
                            violation_type=ViolationType.CRUD_FLS_VIOLATION,
                            file_name=self.file_name,
                            line_number=i + 1,
                            code_snippet=line.strip(),
                            recommendation=recommendation_text,
                            criticality=severity
                        ))
    
    def _check_soql_injection(self):
        """
        Check for potential SOQL injection vulnerabilities
        
        Only flags TRUE injection risks:
        - Database.query() with string concatenation (without escapeSingleQuotes)
        - WHERE/FROM clause with string concatenation (without bind variables)
        
        Does NOT flag:
        - Bind variables (:accountId)
        - Field expressions in SELECT (Amount__c + Tax__c)
        - String literals in SELECT ('Status: ' + Status__c)
        - String.escapeSingleQuotes usage
        - Test-only helper code
        - Dynamic object/field access constrained by Schema describe/global describe
        """
        if self._is_test_class():
            return

        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            line_upper = line.upper()
            is_vulnerable = False
            reason = ""
            
            # Pattern 1: Database.query() with string concatenation
            if 'DATABASE.QUERY' in line_upper and '+' in line and ("'" in line or '"' in line):
                # Check if NOT using escapeSingleQuotes
                if 'String.escapeSingleQuotes'.lower() not in line.lower():
                    if not self._has_schema_constrained_dynamic_query_context(i):
                        is_vulnerable = True
                        reason = "Database.query() with string concatenation"
            
            # Pattern 2: Inline SOQL [SELECT...] with string concatenation in WHERE/FROM
            elif '[SELECT' in line_upper and '+' in line and ("'" in line or '"' in line):
                # Find clause positions
                where_idx = line_upper.find('WHERE')
                from_idx = line_upper.find('FROM')
                select_idx = line_upper.find('[SELECT')
                
                # Check WHERE clause for string concatenation
                if where_idx != -1:
                    where_part = line[where_idx:]
                    # If WHERE has '+' and quotes, check for bind variables
                    if '+' in where_part and ("'" in where_part or '"' in where_part):
                        # If no bind variable (:var), it's likely vulnerable
                        # Check if the '+' is between quotes (string concat)
                        # Pattern: '...' + variable + '...'
                        concat_pattern = r"['\"].*\+|^\+.*['\"]"
                        if re.search(concat_pattern, where_part):
                            # Likely string concatenation in WHERE clause
                            is_vulnerable = True
                            reason = "String concatenation in WHERE clause"
                
                # Check FROM clause for string concatenation (dynamic object name)
                elif from_idx != -1 and where_idx == -1:
                    from_part = line[from_idx:]
                    if '+' in from_part and ("'" in from_part or '"' in from_part):
                        # Dynamic object/table name - dangerous
                        if not self._has_schema_constrained_dynamic_query_context(i):
                            is_vulnerable = True
                            reason = "String concatenation in FROM clause"
                
                # If '+' is only in SELECT clause, it's likely safe (field expression)
                # Don't flag these
            
            # Pattern 3: String variable building SOQL with concatenation
            elif ('string' in line_upper and '=' in line and 'select' in line_upper and 
                  '+' in line and ("'" in line or '"' in line)):
                # Check if building dynamic SOQL string
                # e.g., String query = 'SELECT ... ' + variable
                if 'String.escapeSingleQuotes'.lower() not in line.lower():
                    # Look for pattern: 'SELECT ... FROM ... WHERE ...' + 
                    if re.search(r"['\"]SELECT.*['\"].*\+", line, re.IGNORECASE):
                        if not self._has_schema_constrained_dynamic_query_context(i):
                            is_vulnerable = True
                            reason = "Dynamic SOQL string with concatenation"
            
            if is_vulnerable:
                self.violations.append(Violation(
                    violation_type=ViolationType.SOQL_INJECTION,
                    file_name=self.file_name,
                    line_number=i + 1,
                    code_snippet=line.strip(),
                    recommendation=f"SOQL Injection Risk ({reason}): Use bind variables (:variable) instead of string concatenation. For dynamic queries, use String.escapeSingleQuotes() or consider Type.forName() for dynamic sObject access.",
                    criticality="Critical"
                ))

    def _is_test_class(self) -> bool:
        """Return True for Apex test classes that should not drive runtime security findings."""
        file_name_lower = self.file_name.lower()
        code_lower = self.code.lower()
        return '@istest' in code_lower or file_name_lower.endswith('test.cls') or '_test' in file_name_lower

    def _has_schema_constrained_dynamic_query_context(self, line_index: int) -> bool:
        """
        Detect dynamic SOQL that is constrained by schema metadata or an explicit allowlist.

        This suppresses false positives for patterns such as:
        - Schema/global describe validated object names
        - Describe-backed field selection
        - Regex allowlists combined with global describe checks
        """
        start = max(0, line_index - 120)
        end = min(len(self.lines), line_index + 20)
        context = '\n'.join(self.lines[start:end]).lower()

        has_global_describe = (
            'schema.getglobaldescribe' in context or
            'getglobaldescribemap' in context
        )
        has_describe_field_map = (
            'getdescribe().fields.getmap()' in context or
            '.getdescribe().fields.getmap()' in context
        )
        has_allowlist_regex = 'pattern.compile(' in context and 'matcher(' in context
        has_reference_describe = 'getreferenceto()' in context
        has_describe_backed_object_instantiation = '.newsobject()' in context or 'getallfields(' in context

        return (
            (has_global_describe and has_describe_field_map) or
            (has_global_describe and has_allowlist_regex) or
            (has_global_describe and has_reference_describe) or
            (has_global_describe and has_describe_backed_object_instantiation)
        )
    
    def _determine_sharing_severity(self, class_name: str, class_body: str):
        """
        Determine severity of missing sharing keyword based on class context
        
        SKIP (None): Test classes, interfaces, exceptions, pure wrapper/data-holder classes
        🔴 Critical: @AuraEnabled controllers, REST APIs, global classes
        🔵 Low: Batch/Queueable/Schedulable (system mode by design)
        🟡 Medium: Standard internal classes (should use inherited sharing)
        """
        code_lower = self.code.lower()
        class_body_lower = class_body.lower()
        file_name_lower = self.file_name.lower()
        
        # SKIP: Test Classes
        if '@istest' in code_lower:
            return None, "Test class (Skip)"
        
        # SKIP: Interfaces and Exceptions
        if 'interface' in code_lower or 'extends exception' in code_lower:
            return None, "Interface/Exception (Skip)"

        # SKIP: Pure wrapper/data-holder classes inherit the parent's effective execution context
        if self._is_wrapper_data_holder_class(class_name, class_body):
            return None, "Wrapper/Data-holder class (Skip)"
        
        # 🔴 CRITICAL: Public Entry Points (High Risk)
        
        # Controllers with @AuraEnabled
        if '@auraenabled' in class_body_lower:
            return "Critical", "Unsecured Controller (@AuraEnabled). Public entry point missing sharing keyword."
        
        # REST API Endpoints
        if any(keyword in class_body_lower for keyword in ['@restresource', '@httppost', '@httpget', '@httpput', '@httpdelete', '@httppatch']):
            return "Critical", "Unsecured API Endpoint. External entry point missing sharing keyword."
        
        # Global Classes
        if 'global class' in class_body_lower:
            return "Critical", "Unsecured Global Class. Accessible across namespaces/packages without sharing."
        
        # 🔵 LOW: Automation/Async (Batch, Queueable, Schedulable)
        # These run in System Mode by design (backend processes)
        if any(keyword in class_body_lower for keyword in ['database.batchable', 'queueable', 'schedulable']):
            return "Low", "Automation class runs in System Mode by default. Best Practice: Explicitly add 'without sharing' to denote intent."
        
        # 🟡 MEDIUM: Standard Internal Classes
        # Domain logic or Service classes should use 'inherited sharing'
        return "Medium", "Class implicitly runs in System Mode. Recommended: Add 'inherited sharing' to respect caller security."
    
    def _check_missing_sharing(self):
        """Check for missing sharing keywords in class declarations with context-aware severity"""
        class_pattern = re.compile(r'^\s*(?:public|global)\s+class\s+(\w+)', re.IGNORECASE)
        file_name_lower = self.file_name.lower()

        if any(token in file_name_lower for token in ['wrapper', 'request', 'response', 'dto', 'payload', 'result', 'data']):
            return
        
        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            match = class_pattern.search(line)
            if match:
                class_name = match.group(1)
                # Check if it has 'with sharing', 'without sharing', or 'inherited sharing'
                if 'sharing' not in line.lower():
                    class_end_index = self._find_class_end(i)
                    class_body = '\n'.join(self.lines[i:class_end_index + 1])

                    # Determine context-aware severity
                    severity, reason = self._determine_sharing_severity(class_name, class_body)
                    
                    # Skip if severity is None (test classes, interfaces, etc.)
                    if severity is None:
                        continue
                    
                    # Build recommendation based on severity
                    if severity == "Critical":
                        recommendation = f"{reason}\n\nRecommendation: Add 'with sharing' keyword immediately:\n  public with sharing class ClassName {{\n    // This enforces record-level security\n  }}"
                    elif severity == "Low":
                        recommendation = f"{reason}\n\nRecommendation: Explicitly add 'without sharing' to document intent:\n  public without sharing class ClassName implements Database.Batchable<SObject> {{\n    // System mode is expected for batch processes\n  }}"
                    else:  # Medium
                        recommendation = f"{reason}\n\nRecommendation: Add 'inherited sharing' to respect caller security:\n  public inherited sharing class ClassName {{\n    // Security context inherited from caller\n  }}"
                    
                    self.violations.append(Violation(
                        violation_type=ViolationType.MISSING_SHARING,
                        file_name=self.file_name,
                        line_number=i + 1,
                        code_snippet=line.strip(),
                        recommendation=recommendation,
                        criticality=severity
                    ))

    def _find_class_end(self, start_index: int) -> int:
        """Find the end line for a class block using brace depth."""
        brace_depth = 0
        seen_open = False
        for i in range(start_index, len(self.lines)):
            line = re.sub(r'//.*', '', self.lines[i])
            brace_depth += line.count('{')
            if '{' in line:
                seen_open = True
            brace_depth -= line.count('}')
            if seen_open and brace_depth <= 0:
                return i
        return len(self.lines) - 1

    def _is_wrapper_data_holder_class(self, class_name: str, class_body: str) -> bool:
        """
        Skip wrapper/data-holder classes.

        Wrapper-style classes are typically DTO/request/response containers whose
        practical execution context is inherited from surrounding Apex flow, so
        flagging missing sharing adds noise.
        """
        class_name_lower = class_name.lower()

        wrapper_like_name = any(token in class_name_lower for token in [
            'wrapper', 'request', 'response', 'dto', 'payload', 'result', 'data'
        ])

        return wrapper_like_name
    
    def _check_hardcoded_credentials(self):
        """Check for hardcoded credentials, API keys, tokens"""
        sensitive_patterns = [
            (r'password\s*=\s*[\'"][^\'"]+[\'"]', 'password'),
            (r'apikey\s*=\s*[\'"][^\'"]+[\'"]', 'API key'),
            (r'api_key\s*=\s*[\'"][^\'"]+[\'"]', 'API key'),
            (r'secret\s*=\s*[\'"][^\'"]+[\'"]', 'secret'),
            (r'token\s*=\s*[\'"][^\'"]+[\'"]', 'token'),
            (r'bearer\s+[\'"][^\'"]+[\'"]', 'bearer token'),
            (r'authorization\s*=\s*[\'"][^\'"]+[\'"]', 'authorization header')
        ]
        
        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            for pattern, cred_type in sensitive_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Skip if it's a placeholder or variable
                    if 'xxx' not in line.lower() and 'test' not in line.lower() and 'example' not in line.lower():
                        self.violations.append(Violation(
                            violation_type=ViolationType.HARDCODED_CREDENTIALS,
                            file_name=self.file_name,
                            line_number=i + 1,
                            code_snippet=line.strip()[:100] + '...' if len(line.strip()) > 100 else line.strip(),
                            recommendation=f"Remove hardcoded {cred_type}. Use Named Credentials, Custom Settings, or Custom Metadata Types",
                            criticality="Critical"
                        ))
                        break
    
    def _check_system_debug_sensitive(self):
        """Check for System.debug with potentially sensitive data"""
        debug_pattern = re.compile(r'System\.debug', re.IGNORECASE)
        sensitive_keywords = ['password', 'apikey', 'api_key', 'secret', 'token', 'ssn', 'credit', 'card']
        
        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            if debug_pattern.search(line):
                line_lower = line.lower()
                if any(keyword in line_lower for keyword in sensitive_keywords):
                    self.violations.append(Violation(
                        violation_type=ViolationType.SYSTEM_DEBUG_SENSITIVE,
                        file_name=self.file_name,
                        line_number=i + 1,
                        code_snippet=line.strip(),
                        recommendation="Remove System.debug statements with sensitive data or use proper logging framework",
                        criticality="Low"
                    ))
    
    def _check_generic_exceptions(self):
        """Check for overly broad exception handling"""
        generic_catch_pattern = re.compile(r'catch\s*\(\s*Exception\s+\w+\s*\)', re.IGNORECASE)
        
        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            if generic_catch_pattern.search(line):
                self.violations.append(Violation(
                    violation_type=ViolationType.GENERIC_EXCEPTION,
                    file_name=self.file_name,
                    line_number=i + 1,
                    code_snippet=line.strip(),
                    recommendation="Catch specific exception types (DmlException, QueryException, etc.) instead of generic Exception",
                    criticality="Low"
                ))
    
    def _check_recursive_triggers(self):
        """Check for potential recursive trigger patterns"""
        # Only check if this is a trigger file
        if 'trigger' not in self.file_name.lower():
            return
        
        # Look for trigger without recursion control
        has_static_boolean = False
        has_handler_pattern = False
        
        for line in self.lines:
            if 'static' in line.lower() and 'boolean' in line.lower():
                has_static_boolean = True
            if 'handler' in line.lower() or 'triggerhandler' in line.lower():
                has_handler_pattern = True
        
        # Check if trigger has DML or callouts without recursion control
        has_dml = False
        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            if re.search(r'\b(insert|update|delete|upsert)\s+', line, re.IGNORECASE):
                has_dml = True
                
                if not has_static_boolean and not has_handler_pattern:
                    self.violations.append(Violation(
                        violation_type=ViolationType.RECURSIVE_TRIGGER,
                        file_name=self.file_name,
                        line_number=i + 1,
                        code_snippet=line.strip(),
                        recommendation="Implement recursion control using static boolean or trigger handler pattern to prevent infinite loops",
                        criticality="High"
                    ))
                    break
    
    def _check_mixed_dml(self):
        """Check for mixed DML operations (setup and non-setup objects)"""
        # Setup objects
        setup_objects = ['User', 'Group', 'GroupMember', 'QueueSobject', 'PermissionSet', 
                        'PermissionSetAssignment', 'UserRole', 'Profile']
        
        has_setup_dml = False
        has_regular_dml = False
        setup_line = 0
        regular_line = 0
        
        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            if re.search(r'\b(insert|update|delete|upsert)\s+', line, re.IGNORECASE):
                # Check if it's a setup object
                is_setup = any(obj in line for obj in setup_objects)
                
                if is_setup:
                    has_setup_dml = True
                    setup_line = i + 1
                else:
                    has_regular_dml = True
                    regular_line = i + 1
        
        # Report if both types found in same class
        if has_setup_dml and has_regular_dml:
            self.violations.append(Violation(
                violation_type=ViolationType.MIXED_DML,
                file_name=self.file_name,
                line_number=regular_line,
                code_snippet=f"Mixed DML detected (setup DML at line {setup_line}, regular DML at line {regular_line})",
                recommendation="Separate setup object DML from regular object DML using @future or Queueable",
                criticality="Low"
            ))
    
    def _check_nested_loops(self):
        """Check for nested loops that might contain SOQL/DML"""
        # Find nested loops (loop within loop)
        nested_loops = []
        for i in range(len(self.loops)):
            start1, end1 = self.loops[i]
            for j in range(i + 1, len(self.loops)):
                start2, end2 = self.loops[j]
                if start1 < start2 and end2 < end1:
                    nested_loops.append((start1, end1, start2, end2))

        # Dedupe so an offending line that lives inside multiple inner loops
        # is reported once per actual line, with Critical severity (matching
        # the rules-reference catalog).
        reported_lines: Set[int] = set()
        for outer_start, outer_end, inner_start, inner_end in nested_loops:
            for line_num in range(inner_start, min(inner_end + 1, len(self.lines))):
                if line_num in reported_lines:
                    continue
                line = self.lines[line_num]
                if CodePreprocessor.is_single_line_comment(line):
                    continue

                query = SOQLDetector.collect_query_execution(self.lines, line_num, include_dynamic=True)
                has_soql = bool(query and query['start_line'] == line_num and query['end_line'] <= inner_end)
                if has_soql or DMLDetector.is_dml_statement(line):
                    reported_lines.add(line_num)
                    self.violations.append(Violation(
                        violation_type=ViolationType.NESTED_LOOPS,
                        file_name=self.file_name,
                        line_number=line_num + 1,
                        code_snippet=line.strip(),
                        recommendation="Avoid SOQL/DML in nested loops. Use maps/sets to collect IDs and query once outside loops",
                        criticality="Critical"
                    ))

    def _check_schema_getglobaldescribe_in_loops(self):
        """Check for Schema.getGlobalDescribe() usage inside loops"""
        pattern = re.compile(r'\bSchema\.getGlobalDescribe\s*\(', re.IGNORECASE)

        reported_lines: Set[int] = set()
        for start_line, end_line in self.loops:
            for i in range(start_line + 1, end_line):
                if i in reported_lines:
                    continue
                line = self.lines[i]
                if CodePreprocessor.is_single_line_comment(line):
                    continue

                if pattern.search(line):
                    reported_lines.add(i)
                    self.violations.append(Violation(
                        violation_type=ViolationType.SCHEMA_GLOBAL_DESCRIBE_IN_LOOP,
                        file_name=self.file_name,
                        line_number=i + 1,
                        code_snippet=line.strip(),
                        recommendation="Move Schema.getGlobalDescribe() outside the loop and cache the result in a map for reuse.",
                        criticality="High"
                    ))

    def _check_inefficient_global_describe_usage(self):
        """Check for repeated uncached Schema.getGlobalDescribe() usage"""
        pattern = re.compile(r'\bSchema\.getGlobalDescribe\s*\(', re.IGNORECASE)
        occurrences = []

        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue
            if pattern.search(line):
                occurrences.append(i)

        if len(occurrences) <= 1:
            return

        for i in occurrences[1:]:
            self.violations.append(Violation(
                violation_type=ViolationType.SCHEMA_GLOBAL_DESCRIBE_NOT_EFFICIENT,
                file_name=self.file_name,
                line_number=i + 1,
                code_snippet=self.lines[i].strip(),
                recommendation="Cache Schema.getGlobalDescribe() in a local/static variable instead of calling it repeatedly.",
                criticality="Medium"
            ))

    def _check_redundant_soql(self):
        """Check for duplicate inline SOQL queries repeated in the same class"""
        seen_queries = {}

        for query in self._collect_soql_queries():
            query_text = query['full_query']
            select_start = query_text.upper().find('[SELECT')
            if select_start != -1:
                query_text = query_text[select_start:]
            normalized = re.sub(r'\s+', ' ', query_text).strip().lower()
            if normalized in seen_queries:
                self.violations.append(Violation(
                    violation_type=ViolationType.REDUNDANT_SOQL,
                    file_name=self.file_name,
                    line_number=query['start_line'] + 1,
                    code_snippet=query['line'].strip(),
                    recommendation="Avoid repeating the same SOQL query. Reuse the previously queried records or cache the results.",
                    criticality="Medium"
                ))
            else:
                seen_queries[normalized] = query['start_line']

    def _check_sobject_map_in_for_loop(self):
        """Check for manual SObject map construction inside for-each loops"""
        foreach_pattern = re.compile(r'for\s*\(\s*[\w<>,\s]+\s+(\w+)\s*:\s*(\w+)\s*\)', re.IGNORECASE)

        for start_line, end_line in self.loops:
            header = self.lines[start_line]
            match = foreach_pattern.search(header)
            if not match:
                continue

            loop_var = match.group(1)
            put_pattern = re.compile(
                rf'\.\s*put\s*\(\s*{re.escape(loop_var)}\.Id\s*,\s*{re.escape(loop_var)}\s*\)\s*;',
                re.IGNORECASE
            )

            for i in range(start_line + 1, end_line):
                line = self.lines[i]
                if CodePreprocessor.is_single_line_comment(line):
                    continue
                if put_pattern.search(line):
                    self.violations.append(Violation(
                        violation_type=ViolationType.SOBJECT_MAP_IN_FOR_LOOP,
                        file_name=self.file_name,
                        line_number=i + 1,
                        code_snippet=line.strip(),
                        recommendation="Replace manual map.put(record.Id, record) loops with new Map<Id, SObject>(records) when building an SObject map.",
                        criticality="Medium"
                    ))
                    break

    def _check_soql_with_negative_expressions(self):
        """Check for SOQL filters using negative expressions"""
        negative_pattern = re.compile(r'\bWHERE\b.*(?:!=|<>|\bNOT\s+LIKE\b|\bNOT\s+IN\b|\bEXCLUDES\b)', re.IGNORECASE | re.DOTALL)

        for query in self._collect_soql_queries():
            if negative_pattern.search(query['full_query']):
                self.violations.append(Violation(
                    violation_type=ViolationType.SOQL_WITH_NEGATIVE_EXPRESSIONS,
                    file_name=self.file_name,
                    line_number=query['start_line'] + 1,
                    code_snippet=query['line'].strip(),
                    recommendation="Avoid negative SOQL predicates when possible. Prefer selective positive filters to improve query performance.",
                    criticality="Medium"
                ))

    def _check_soql_with_unused_fields(self):
        """Check for simple SOQL queries selecting fields that are never referenced later in the method"""
        foreach_pattern_template = r'for\s*\(\s*[\w<>,\s]+\s+(\w+)\s*:\s*{var}\s*\)'

        for query in self._collect_soql_queries():
            assigned_var = query['assigned_var']
            if not assigned_var:
                continue

            selected_fields = self._extract_simple_select_fields(query['full_query'])
            if len(selected_fields) < 2:
                continue

            method_end = self._find_enclosing_method_end(query['start_line'])
            search_lines = self.lines[query['end_line'] + 1:method_end + 1]
            used_fields = set()
            uncertain_usage = False

            direct_usage_pattern = re.compile(rf'\b{re.escape(assigned_var)}\.(\w+)\b')
            foreach_pattern = re.compile(foreach_pattern_template.format(var=re.escape(assigned_var)), re.IGNORECASE)

            for offset, line in enumerate(search_lines, start=query['end_line'] + 1):
                if CodePreprocessor.is_single_line_comment(line):
                    continue

                if re.search(rf'\breturn\s+{re.escape(assigned_var)}\b', line):
                    uncertain_usage = True
                    break

                for field in direct_usage_pattern.findall(line):
                    used_fields.add(field)

                loop_match = foreach_pattern.search(line)
                if loop_match:
                    loop_var = loop_match.group(1)
                    loop_end = self._find_loop_end_from_header(offset)
                    loop_var_field_pattern = re.compile(rf'\b{re.escape(loop_var)}\.(\w+)\b')
                    whole_record_pattern = re.compile(rf'\b\w+\s*\([^)]*\b{re.escape(loop_var)}\b[^)]*\)')
                    for body_index in range(offset + 1, loop_end + 1):
                        body_line = self.lines[body_index]
                        if CodePreprocessor.is_single_line_comment(body_line):
                            continue
                        if whole_record_pattern.search(body_line) and not loop_var_field_pattern.search(body_line):
                            uncertain_usage = True
                            break
                        for field in loop_var_field_pattern.findall(body_line):
                            used_fields.add(field)
                    if uncertain_usage:
                        break

            if uncertain_usage or not used_fields:
                continue

            unused_fields = [field for field in selected_fields if field not in used_fields]
            if unused_fields:
                self.violations.append(Violation(
                    violation_type=ViolationType.SOQL_WITH_UNUSED_FIELDS,
                    file_name=self.file_name,
                    line_number=query['start_line'] + 1,
                    code_snippet=query['line'].strip(),
                    recommendation=f"Remove unused SOQL fields when possible. Unused fields detected: {', '.join(unused_fields[:5])}.",
                    criticality="Medium"
                ))

    def _check_soql_with_wildcard_filter(self):
        """Check for SOQL LIKE filters with wildcard literals"""
        wildcard_pattern = re.compile(r'\bLIKE\s+[\'"][^\'"]*%[^\'"]*[\'"]', re.IGNORECASE)

        for query in self._collect_soql_queries():
            if wildcard_pattern.search(query['full_query']):
                self.violations.append(Violation(
                    violation_type=ViolationType.SOQL_WITH_WILDCARD_FILTER,
                    file_name=self.file_name,
                    line_number=query['start_line'] + 1,
                    code_snippet=query['line'].strip(),
                    recommendation="Wildcard LIKE filters can be unselective. Prefer exact or prefix-selective filters when possible.",
                    criticality="Medium"
                ))

    def _check_soql_with_apex_filter(self):
        """Check for broad SOQL followed by filtering in Apex"""
        assignment_pattern = re.compile(r'(?:List<[^>]+>\s+)?(\w+)\s*=\s*\[\s*SELECT\b', re.IGNORECASE)
        foreach_pattern_template = r'for\s*\([^:]+:\s*{var}\s*\)'

        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            if CodePreprocessor.is_single_line_comment(line):
                i += 1
                continue

            match = assignment_pattern.search(line)
            if not match:
                i += 1
                continue

            collection_var = match.group(1)
            query_lines = [line]
            query_start = i
            bracket_count = line.count('[') - line.count(']')
            j = i

            if bracket_count > 0 and ';' not in line:
                j = i + 1
                while j < len(self.lines) and j < i + 30:
                    query_lines.append(self.lines[j])
                    bracket_count += self.lines[j].count('[') - self.lines[j].count(']')
                    if bracket_count <= 0 or ';' in self.lines[j]:
                        break
                    j += 1

            full_query = ' '.join(query_lines)
            has_where = ' where ' in full_query.lower()

            if not has_where:
                foreach_pattern = re.compile(foreach_pattern_template.format(var=re.escape(collection_var)), re.IGNORECASE)
                for k in range(j + 1, min(len(self.lines), j + 20)):
                    next_line = self.lines[k]
                    if CodePreprocessor.is_single_line_comment(next_line):
                        continue
                    if foreach_pattern.search(next_line):
                        loop_end = self._find_loop_end_from_header(k)
                        body_text = ' '.join(self.lines[k:loop_end + 1]).lower()
                        if 'if (' in body_text or 'if(' in body_text:
                            self.violations.append(Violation(
                                violation_type=ViolationType.SOQL_WITH_APEX_FILTER,
                                file_name=self.file_name,
                                line_number=query_start + 1,
                                code_snippet=line.strip(),
                                recommendation="Push filtering into the SOQL WHERE clause instead of querying broadly and filtering records in Apex.",
                                criticality="High"
                            ))
                            break

            i = j + 1

    def _check_expensive_methods_in_loops(self):
        """Check for expensive method calls repeatedly executed inside loops"""
        method_patterns = [
            (re.compile(r'\bSchema\.describeSObjects\s*\(', re.IGNORECASE), 'Schema.describeSObjects()'),
            (re.compile(r'\bJSON\.(serialize|deserialize|deserializeUntyped)\s*\(', re.IGNORECASE), 'JSON serialization/deserialization'),
            (re.compile(r'\bPattern\.compile\s*\(', re.IGNORECASE), 'Pattern.compile()'),
            (re.compile(r'\bType\.forName\s*\(', re.IGNORECASE), 'Type.forName()'),
            (re.compile(r'\bString\.format\s*\(', re.IGNORECASE), 'String.format()')
        ]

        reported_lines: Set[int] = set()
        for start_line, end_line in self.loops:
            for i in range(start_line + 1, end_line):
                if i in reported_lines:
                    continue
                line = self.lines[i]
                if CodePreprocessor.is_single_line_comment(line):
                    continue

                for pattern, label in method_patterns:
                    if pattern.search(line):
                        reported_lines.add(i)
                        self.violations.append(Violation(
                            violation_type=ViolationType.EXPENSIVE_METHODS_IN_LOOP,
                            file_name=self.file_name,
                            line_number=i + 1,
                            code_snippet=line.strip(),
                            recommendation=f"Avoid repeated {label} calls inside loops. Compute once outside the loop and reuse the result.",
                            criticality="High"
                        ))
                        break

    def _check_expensive_string_comparison(self):
        """Check for repeated case-normalizing string comparisons"""
        comparison_tokens = ['==', '!=', '.equals(', '.contains(', '.startswith(', '.endswith(']

        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue

            lowered = line.lower()
            if ('.tolowercase()' in lowered or '.touppercase()' in lowered) and any(token in lowered for token in comparison_tokens):
                self.violations.append(Violation(
                    violation_type=ViolationType.EXPENSIVE_STRING_COMPARISON,
                    file_name=self.file_name,
                    line_number=i + 1,
                    code_snippet=line.strip(),
                    recommendation="Avoid repeated toLowerCase()/toUpperCase() during comparisons. Normalize once or use equalsIgnoreCase() where appropriate.",
                    criticality="Medium"
                ))

    def _check_copying_elements_with_for_loop(self):
        """Check for direct element-by-element list copying in for-each loops"""
        foreach_pattern = re.compile(r'for\s*\(\s*[\w<>,\s]+\s+(\w+)\s*:\s*(\w+)\s*\)', re.IGNORECASE)

        for start_line, end_line in self.loops:
            header = self.lines[start_line]
            match = foreach_pattern.search(header)
            if not match:
                continue

            loop_var = match.group(1)
            add_pattern = re.compile(rf'\.\s*add\s*\(\s*{re.escape(loop_var)}\s*\)\s*;', re.IGNORECASE)
            meaningful_lines = []
            offending_index = None

            for i in range(start_line + 1, end_line):
                line = self.lines[i]
                stripped = line.strip()
                if not stripped or CodePreprocessor.is_single_line_comment(line):
                    continue
                meaningful_lines.append(stripped)
                if offending_index is None and add_pattern.search(line):
                    offending_index = i

            if offending_index is not None and len(meaningful_lines) == 1:
                self.violations.append(Violation(
                    violation_type=ViolationType.COPYING_ELEMENTS_WITH_FOR_LOOP,
                    file_name=self.file_name,
                    line_number=offending_index + 1,
                    code_snippet=self.lines[offending_index].strip(),
                    recommendation="Replace manual element-by-element copying with addAll() or direct collection assignment when no transformation is needed.",
                    criticality="Medium"
                ))

    def _check_sorting_in_apex(self):
        """Check for list sorting in Apex when ORDER BY could be pushed to SOQL"""
        assignment_pattern = re.compile(r'(?:List<[^>]+>\s+)?(\w+)\s*=\s*\[\s*SELECT\b', re.IGNORECASE)
        sort_pattern_template = r'\b{var}\.sort\s*\(\s*\)\s*;'

        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            if CodePreprocessor.is_single_line_comment(line):
                i += 1
                continue

            match = assignment_pattern.search(line)
            if not match:
                i += 1
                continue

            collection_var = match.group(1)
            query_lines = [line]
            bracket_count = line.count('[') - line.count(']')
            j = i

            if bracket_count > 0 and ';' not in line:
                j = i + 1
                while j < len(self.lines) and j < i + 30:
                    query_lines.append(self.lines[j])
                    bracket_count += self.lines[j].count('[') - self.lines[j].count(']')
                    if bracket_count <= 0 or ';' in self.lines[j]:
                        break
                    j += 1

            full_query = ' '.join(query_lines).lower()
            if ' order by ' not in full_query:
                sort_pattern = re.compile(sort_pattern_template.format(var=re.escape(collection_var)), re.IGNORECASE)
                for k in range(j + 1, min(len(self.lines), j + 20)):
                    if sort_pattern.search(self.lines[k]):
                        self.violations.append(Violation(
                            violation_type=ViolationType.SORTING_IN_APEX,
                            file_name=self.file_name,
                            line_number=k + 1,
                            code_snippet=self.lines[k].strip(),
                            recommendation="Prefer ORDER BY in SOQL instead of sorting queried records in Apex when the desired sort is database-driven.",
                            criticality="Medium"
                        ))
                        break

            i = j + 1

    def _check_busy_loop_delay(self):
        """Check for loops used as manual delays/spin-waits"""
        busy_loop_patterns = [
            re.compile(r'^\s*while\s*\([^)]*(system|datetime)\.now\s*\(', re.IGNORECASE),
            re.compile(r'^\s*while\s*\([^)]*limits\.getcputime\s*\(', re.IGNORECASE)
        ]

        for start_line, end_line in self.loops:
            header = self.lines[start_line]
            header_lower = header.lower()
            matched = any(pattern.search(header) for pattern in busy_loop_patterns)

            if not matched:
                if header_lower.strip().startswith('do'):
                    trailer = self.lines[end_line].lower()
                    matched = (
                        'system.now()' in trailer or
                        'datetime.now()' in trailer or
                        'limits.getcputime()' in trailer
                    )
                else:
                    matched = (
                        'system.now()' in header_lower or
                        'datetime.now()' in header_lower or
                        'limits.getcputime()' in header_lower
                    )

            if not matched:
                continue

            body_lines = [
                self.lines[i].strip() for i in range(start_line + 1, end_line)
                if self.lines[i].strip() and not CodePreprocessor.is_single_line_comment(self.lines[i])
            ]
            if len(body_lines) <= 2:
                self.violations.append(Violation(
                    violation_type=ViolationType.BUSY_LOOP_DELAY,
                    file_name=self.file_name,
                    line_number=start_line + 1,
                    code_snippet=header.strip(),
                    recommendation="Avoid using loops as delays/spin-waits. Use asynchronous designs, scheduled execution, or event-driven coordination instead.",
                    criticality="High"
                ))

    def _check_limits_getheapsize_in_loop(self):
        """Check for Limits.getHeapSize()/getLimitHeapSize() inside loops"""
        pattern = re.compile(r'\bLimits\.(getHeapSize|getLimitHeapSize)\s*\(', re.IGNORECASE)

        reported_lines: Set[int] = set()
        for start_line, end_line in self.loops:
            for i in range(start_line + 1, end_line):
                if i in reported_lines:
                    continue
                line = self.lines[i]
                if CodePreprocessor.is_single_line_comment(line):
                    continue
                if pattern.search(line):
                    reported_lines.add(i)
                    self.violations.append(Violation(
                        violation_type=ViolationType.LIMITS_GET_HEAP_SIZE_IN_LOOP,
                        file_name=self.file_name,
                        line_number=i + 1,
                        code_snippet=line.strip(),
                        recommendation="Avoid repeatedly checking heap size inside loops. Monitor once outside the loop or refactor to reduce heap pressure.",
                        criticality="Medium"
                    ))

    def _check_unused_methods(self):
        """Check for private methods that are never referenced within the class"""
        method_pattern = re.compile(
            r'^\s*private\s+(?:static\s+)?(?:virtual\s+|override\s+)?[\w<>,\[\]\s]+\s+(\w+)\s*\(',
            re.IGNORECASE
        )
        class_name_pattern = re.compile(r'^\s*(?:public|private|protected|global)?\s*class\s+(\w+)', re.IGNORECASE)

        class_name = None
        for line in self.lines:
            match = class_name_pattern.search(line)
            if match:
                class_name = match.group(1)
                break

        private_methods = []
        for i, line in enumerate(self.lines):
            if CodePreprocessor.is_single_line_comment(line):
                continue
            match = method_pattern.search(line)
            if not match:
                continue
            method_name = match.group(1)
            if class_name and method_name == class_name:
                continue
            if i > 0 and '@testvisible' in self.lines[i - 1].lower():
                continue
            private_methods.append((i, method_name))

        for line_index, method_name in private_methods:
            usage_pattern = re.compile(rf'\b{re.escape(method_name)}\s*\(', re.IGNORECASE)
            usage_count = 0
            for i, line in enumerate(self.lines):
                if CodePreprocessor.is_single_line_comment(line):
                    continue
                if usage_pattern.search(line):
                    usage_count += 1
            if usage_count <= 1:
                self.violations.append(Violation(
                    violation_type=ViolationType.UNUSED_METHODS,
                    file_name=self.file_name,
                    line_number=line_index + 1,
                    code_snippet=self.lines[line_index].strip(),
                    recommendation="Remove unused private methods or wire them into the class logic if they are still needed.",
                    criticality="Low"
                ))

    def _find_loop_end_from_header(self, start_index: int) -> int:
        """Find the matching end for a loop header line"""
        for loop_start, loop_end in self.loops:
            if loop_start == start_index:
                return loop_end
        return start_index


class TriggerAnalyzer:
    """Specialized analyzer for Apex Triggers"""
    
    ASYNC_PATTERNS = [
        re.compile(r'Database\.executeBatch\s*\(', re.IGNORECASE),
        re.compile(r'System\.enqueueJob\s*\(', re.IGNORECASE),
        re.compile(r'@future', re.IGNORECASE)
    ]
    
    def __init__(self, file_name: str, code: str):
        self.file_name = file_name
        self.code = code
        self.lines = CodePreprocessor.preprocess_code(code)
        self.violations: List[Violation] = []
    
    def analyze(self) -> List[Violation]:
        """Analyze trigger for async operations"""
        for i, line in enumerate(self.lines):
            # Skip single-line comments but keep line numbers accurate
            if CodePreprocessor.is_single_line_comment(line):
                continue
            
            for pattern in self.ASYNC_PATTERNS:
                if pattern.search(line):
                    self.violations.append(Violation(
                        violation_type=ViolationType.ASYNC_IN_TRIGGER,
                        file_name=self.file_name,
                        line_number=i + 1,  # Use original line number (1-indexed)
                        code_snippet=line.strip(),
                        recommendation="Move async operations to a handler class to improve maintainability",
                        criticality="High"
                    ))
        
        return self.violations


class TestClassAnalyzer:
    """Specialized analyzer for Test Classes"""
    
    def __init__(self, file_name: str, code: str):
        self.file_name = file_name
        self.code = code
        self.lines = CodePreprocessor.preprocess_code(code)
        self.violations: List[Violation] = []
    
    def analyze(self) -> List[Violation]:
        """Run test class specific checks"""
        self._check_missing_assertions()
        self._check_see_all_data()
        self._check_persona_based_testing()
        
        return self.violations
    
    def _check_missing_assertions(self):
        """Check for test methods without assertions"""
        # Find test methods
        test_method_pattern = re.compile(r'(?:@isTest|testMethod)\s+(?:static\s+)?(?:void|testMethod)\s+(\w+)', re.IGNORECASE)
        assert_patterns = [
            re.compile(r'System\.assert', re.IGNORECASE),
            re.compile(r'System\.assertEquals', re.IGNORECASE),
            re.compile(r'System\.assertNotEquals', re.IGNORECASE),
            re.compile(r'Assert\.', re.IGNORECASE)
        ]
        
        test_methods = []
        for i, line in enumerate(self.lines):
            if test_method_pattern.search(line):
                test_methods.append((i, line))
        
        # Check each test method for assertions
        for test_line_num, test_line in test_methods:
            has_assertion = False
            
            # Look ahead in the method (next 50 lines)
            for j in range(test_line_num, min(test_line_num + 50, len(self.lines))):
                line = self.lines[j]
                
                # Stop if we hit another method
                if j > test_line_num and ('void' in line or 'testMethod' in line):
                    break
                
                # Check for assertions
                if any(pattern.search(line) for pattern in assert_patterns):
                    has_assertion = True
                    break
            
            if not has_assertion:
                self.violations.append(Violation(
                    violation_type=ViolationType.MISSING_ASSERTIONS,
                    file_name=self.file_name,
                    line_number=test_line_num + 1,
                    code_snippet=test_line.strip(),
                    recommendation="Add System.assert* statements to verify test results",
                    criticality="Low"
                ))
    
    def _check_see_all_data(self):
        """Check for @isTest(SeeAllData=true)"""
        see_all_data_pattern = re.compile(r'@isTest\s*\(\s*SeeAllData\s*=\s*true\s*\)', re.IGNORECASE)
        
        for i, line in enumerate(self.lines):
            if see_all_data_pattern.search(line):
                self.violations.append(Violation(
                    violation_type=ViolationType.SEE_ALL_DATA,
                    file_name=self.file_name,
                    line_number=i + 1,
                    code_snippet=line.strip(),
                    recommendation="Avoid SeeAllData=true. Create test data in the test method for reliable, isolated tests",
                    criticality="Low"
                ))
    
    def _check_persona_based_testing(self):
        """Check for missing persona-based testing (System.runAs)"""
        # Look for test class declaration
        is_test_class = False
        for line in self.lines:
            if re.search(r'@isTest\s*(?:public|private)?\s*class', line, re.IGNORECASE):
                is_test_class = True
                break
        
        if not is_test_class:
            return
        
        # Check if the test class uses System.runAs() for persona-based testing
        has_run_as = False
        run_as_pattern = re.compile(r'System\.runAs\s*\(', re.IGNORECASE)
        
        for line in self.lines:
            if run_as_pattern.search(line):
                has_run_as = True
                break
        
        # If no System.runAs() found, report a violation
        if not has_run_as:
            # Find the class declaration line for reporting
            class_line_num = 0
            for i, line in enumerate(self.lines):
                if re.search(r'@isTest|class\s+\w+', line, re.IGNORECASE):
                    class_line_num = i + 1
                    break
            
            self.violations.append(Violation(
                violation_type=ViolationType.MISSING_PERSONA_TESTING,
                file_name=self.file_name,
                line_number=class_line_num,
                code_snippet=self.lines[class_line_num - 1].strip() if class_line_num > 0 else "",
                recommendation="Add System.runAs() to test with different user personas/profiles. This validates sharing rules, CRUD/FLS, and profile-specific behavior",
                criticality="Medium"
            ))


def analyze_apex_code(file_name: str, code: str, is_trigger: bool = False) -> List[Violation]:
    """
    Main entry point for analyzing Apex code
    
    Args:
        file_name: Name of the file being analyzed
        code: Apex code content
        is_trigger: Whether this is a trigger file
    
    Returns:
        List of violations found
    """
    violations = []
    
    # Run governor limit analysis
    governor_analyzer = GovernorLimitAnalyzer(file_name, code)
    violations.extend(governor_analyzer.analyze())
    
    # Run trigger-specific analysis
    if is_trigger:
        trigger_analyzer = TriggerAnalyzer(file_name, code)
        violations.extend(trigger_analyzer.analyze())
    
    # Run test class analysis
    if '@istest' in code.lower() or 'testmethod' in code.lower():
        test_analyzer = TestClassAnalyzer(file_name, code)
        violations.extend(test_analyzer.analyze())
    
    return violations


# Example usage and testing
if __name__ == "__main__":
    # Test code samples
    test_code_bad = """
    public class TestClass {
        public void badMethod() {
            List<Account> accounts = [SELECT Id FROM Account];
            
            // Bad: DML in loop
            for(Account acc : accounts) {
                insert acc;
            }
            
            // Bad: SOQL in loop
            for(Account acc : accounts) {
                List<Contact> cons = [SELECT Id FROM Contact WHERE AccountId = :acc.Id];
            }
        }
    }
    """
    
    test_code_good = """
    public class TestClass {
        public void goodMethod() {
            // Good: SOQL-for loop
            for(Account acc : [SELECT Id FROM Account]) {
                // Process account
            }
            
            // Good: Bulk DML
            List<Account> accountsToUpdate = new List<Account>();
            for(Account acc : accounts) {
                accountsToUpdate.add(acc);
            }
            update accountsToUpdate;
        }
    }
    """
    
    print("Testing bad code:")
    violations = analyze_apex_code("TestClass.cls", test_code_bad)
    for v in violations:
        print(f"  Line {v.line_number}: {v.violation_type.value} - {v.code_snippet}")
    
    print("\nTesting good code:")
    violations = analyze_apex_code("TestClass.cls", test_code_good)
    print(f"  Found {len(violations)} violations (expected 0)")

