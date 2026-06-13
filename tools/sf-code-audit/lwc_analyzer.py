"""
LWC Analyzer Module
Analyzes Lightning Web Components for security and best practices
"""

import re
from typing import List, Dict


class LWCAnalyzer:
    """Analyzes LWC components for security and best practice issues"""
    
    def __init__(self, component_name: str, js_code: str = "", html_code: str = ""):
        """
        Initialize LWC analyzer
        
        Args:
            component_name: Name of the LWC component
            js_code: JavaScript code
            html_code: HTML template code
        """
        self.component_name = component_name
        self.js_code = js_code
        self.html_code = html_code
        self.issues = []
    
    def analyze(self) -> List[Dict]:
        """
        Run all LWC analysis checks
        
        Returns:
            List of issues found
        """
        self._check_xss_vulnerabilities()
        self._check_error_handling()
        self._check_double_click_prevention()
        self._check_unsafe_html_rendering()
        self._check_insecure_api_calls()
        self._check_console_logs()
        self._check_hardcoded_credentials()
        self._check_improper_data_binding()
        
        return self.issues
    
    def _check_xss_vulnerabilities(self):
        """Check for XSS vulnerabilities (escape={false})"""
        if not self.html_code:
            return
        
        # Check for escape={false} in HTML
        escape_false_pattern = re.compile(r'escape\s*=\s*\{\s*false\s*\}', re.IGNORECASE)
        
        for i, line in enumerate(self.html_code.split('\n'), 1):
            if escape_false_pattern.search(line):
                self.issues.append({
                    'file_name': f"{self.component_name}.html",
                    'type': 'LWC',
                    'line_number': i,
                    'category': 'Security',
                    'rule_name': 'XSS - escape={false}',
                    'criticality': 'High',
                    'snippet': line.strip()[:100],
                    'recommendation': 'Remove escape={false} to prevent XSS vulnerabilities. Use default escaping.'
                })
    
    def _check_error_handling(self):
        """Check for proper error handling in server calls"""
        if not self.js_code:
            return
        
        # Look for promise chains without .catch()
        lines = self.js_code.split('\n')
        for i, line in enumerate(lines, 1):
            # Check for method calls that might be async without error handling
            if re.search(r'\.(then|call)\s*\(', line, re.IGNORECASE):
                # Check if there's a .catch in next few lines
                has_catch = False
                for j in range(i, min(i + 5, len(lines))):
                    if '.catch' in lines[j] or 'catch(' in lines[j]:
                        has_catch = True
                        break
                
                if not has_catch and 'catch' not in line:
                    self.issues.append({
                        'file_name': f"{self.component_name}.js",
                        'type': 'LWC',
                        'line_number': i,
                        'category': 'Best Practices',
                        'rule_name': 'Missing Error Handling',
                        'criticality': 'Medium',
                        'snippet': line.strip()[:100],
                        'recommendation': 'Add .catch() to handle errors from async operations'
                    })
    
    def _check_double_click_prevention(self):
        """Check for double-click prevention in button handlers"""
        if not self.js_code:
            return
        
        lines = self.js_code.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            handler_match = re.search(r'\b(handle\w+)\s*\(', line)
            if not handler_match:
                i += 1
                continue

            handler_name = handler_match.group(1)
            if self._is_non_click_handler(handler_name):
                i += 1
                continue

            handler_start = i
            handler_end = self._find_method_end(lines, handler_start)
            handler_lines = lines[handler_start:handler_end + 1]
            handler_code = '\n'.join(handler_lines)

            if not self._contains_direct_async_action(handler_code):
                i = handler_end + 1
                continue

            if self._has_double_click_guard(handler_code):
                i = handler_end + 1
                continue

            call_line = self._first_async_action_line(handler_lines, handler_start + 1)
            self.issues.append({
                'file_name': f"{self.component_name}.js",
                'type': 'LWC',
                'line_number': call_line,
                'category': 'Best Practices',
                'rule_name': 'Missing Double-Click Prevention',
                'criticality': 'High',
                'snippet': f"{handler_name} - line {call_line}",
                'recommendation': 'Add isLoading/isProcessing guard or disable the action trigger while async work is in progress'
            })
            i = handler_end + 1

    def _is_non_click_handler(self, handler_name: str) -> bool:
        """Skip handlers that are not user actions vulnerable to double-clicking."""
        return bool(re.search(r'(Input|Change|Blur|Focus|Key|FieldEntry|Mouse|Scroll|Hover)$', handler_name))

    def _find_method_end(self, lines: List[str], start_index: int) -> int:
        """Find the end line for a method using brace depth."""
        brace_depth = 0
        seen_open = False
        for i in range(start_index, len(lines)):
            line = re.sub(r'//.*', '', lines[i])
            brace_depth += line.count('{')
            if '{' in line:
                seen_open = True
            brace_depth -= line.count('}')
            if seen_open and brace_depth <= 0:
                return i
        return len(lines) - 1

    def _contains_direct_async_action(self, handler_code: str) -> bool:
        """Detect direct async/network actions instead of comments, logs, or wrapper names."""
        executable_lines = []
        for raw_line in handler_code.split('\n'):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith('//') or stripped.startswith('*'):
                continue
            if 'console.' in stripped:
                continue
            executable_lines.append(stripped)

        executable_code = '\n'.join(executable_lines)
        async_patterns = [
            r'\bawait\b',
            r'\.then\s*\(',
            r'\bfetch\s*\(',
            r'\bXMLHttpRequest\b',
            r'\bupdateRecord\s*\(',
            r'\bcreateRecord\s*\(',
            r'\bdeleteRecord\s*\(',
            r'\brefreshApex\s*\(',
        ]
        return any(re.search(pattern, executable_code, re.IGNORECASE) for pattern in async_patterns)

    def _has_double_click_guard(self, handler_code: str) -> bool:
        """Recognize common loading/disabled guards used to block repeated user actions."""
        guard_patterns = [
            r'\bis(Loading|Processing|Saving|Submitting|OtpVerifying)\s*=\s*true',
            r'\bis(Loading|Processing|Saving|Submitting|OtpVerifying)\s*=\s*false',
            r'\bis\w*Disabled\s*=\s*true',
            r'\bis\w*Disabled\s*=\s*false',
            r'if\s*\(\s*!\s*this\.is\w*Disabled\s*&&\s*!\s*this\.is(Loading|Processing|Saving|Submitting|OtpVerifying)',
            r'if\s*\(\s*this\.is(Loading|Processing|Saving|Submitting|OtpVerifying)\s*\)\s*return',
        ]
        return any(re.search(pattern, handler_code, re.IGNORECASE) for pattern in guard_patterns)

    def _first_async_action_line(self, handler_lines: List[str], start_line_number: int) -> int:
        """Return the first line number in the handler that performs an async/network action."""
        patterns = [
            r'\bawait\b',
            r'\.then\s*\(',
            r'\bfetch\s*\(',
            r'\bXMLHttpRequest\b',
            r'\bupdateRecord\s*\(',
            r'\bcreateRecord\s*\(',
            r'\bdeleteRecord\s*\(',
            r'\brefreshApex\s*\(',
        ]
        for offset, line in enumerate(handler_lines):
            stripped = line.strip()
            if stripped.startswith('//') or 'console.' in stripped:
                continue
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns):
                return start_line_number + offset
        return start_line_number
    
    def _check_unsafe_html_rendering(self):
        """Check for unsafe HTML rendering (innerHTML, dangerouslySetInnerHTML)"""
        if not self.js_code and not self.html_code:
            return
        
        lines = self.js_code.split('\n')
        reported_method_patterns = set()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith('//'):
                continue

            if re.search(r'eval\s*\(', line, re.IGNORECASE):
                self.issues.append({
                    'file_name': f"{self.component_name}.js",
                    'type': 'LWC',
                    'line_number': i,
                    'category': 'Security',
                    'rule_name': 'Unsafe HTML - eval() Usage',
                    'criticality': 'Critical',
                    'snippet': line.strip()[:100],
                    'recommendation': 'Avoid eval() as it can lead to XSS and code execution risks.'
                })
                continue

            if re.search(r'Function\s*\(.*new Function', line, re.IGNORECASE):
                self.issues.append({
                    'file_name': f"{self.component_name}.js",
                    'type': 'LWC',
                    'line_number': i,
                    'category': 'Security',
                    'rule_name': 'Unsafe HTML - new Function()',
                    'criticality': 'High',
                    'snippet': line.strip()[:100],
                    'recommendation': 'Avoid new Function() as it can execute untrusted code.'
                })
                continue

            if re.search(r'dangerouslySetInnerHTML', line, re.IGNORECASE):
                method_name, method_start, method_end = self._find_enclosing_method(lines, i - 1)
                dedupe_key = (method_name or f'line-{i}', 'dangerouslySetInnerHTML')
                if dedupe_key in reported_method_patterns:
                    continue
                reported_method_patterns.add(dedupe_key)
                self.issues.append({
                    'file_name': f"{self.component_name}.js",
                    'type': 'LWC',
                    'line_number': i,
                    'category': 'Security',
                    'rule_name': 'Unsafe HTML - dangerouslySetInnerHTML',
                    'criticality': 'Critical',
                    'snippet': line.strip()[:100],
                    'recommendation': 'Avoid dangerouslySetInnerHTML as it can lead to XSS vulnerabilities. Use safe DOM APIs.'
                })
                continue

            if re.search(r'\.innerHTML\s*=', line, re.IGNORECASE):
                method_name, method_start, method_end = self._find_enclosing_method(lines, i - 1)
                dedupe_key = (method_name or f'line-{i}', 'innerHTML')
                if dedupe_key in reported_method_patterns:
                    continue
                reported_method_patterns.add(dedupe_key)

                severity, recommendation = self._classify_inner_html_usage(lines, i - 1, method_start, method_end)
                self.issues.append({
                    'file_name': f"{self.component_name}.js",
                    'type': 'LWC',
                    'line_number': i,
                    'category': 'Security',
                    'rule_name': 'Unsafe HTML - innerHTML Assignment',
                    'criticality': severity,
                    'snippet': line.strip()[:100],
                    'recommendation': recommendation
                })
    
    def _check_insecure_api_calls(self):
        """Check for insecure API calls and HTTP usage"""
        if not self.js_code:
            return
        
        insecure_patterns = [
            (r'http://', 'HTTP (non-HTTPS)', 'High', 'Use HTTPS for all API calls'),
            (r'fetch\s*\([^)]*http:', 'Insecure fetch()', 'High', 'Use HTTPS endpoints only'),
            (r'XMLHttpRequest', 'XMLHttpRequest', 'Medium', 'Consider using Lightning Data Service or Apex controllers'),
        ]
        
        for i, line in enumerate(self.js_code.split('\n'), 1):
            for pattern, name, criticality, recommendation in insecure_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    self.issues.append({
                        'file_name': f"{self.component_name}.js",
                        'type': 'LWC',
                        'line_number': i,
                        'category': 'Security',
                        'rule_name': name,
                        'criticality': criticality,
                        'snippet': line.strip()[:100],
                        'recommendation': recommendation
                    })

    def _find_enclosing_method(self, lines: List[str], line_index: int):
        """Find the method containing the given line index."""
        method_pattern = re.compile(r'^\s*(?:async\s+)?([A-Za-z_]\w*)\s*\([^)]*\)\s*\{?\s*$')
        for start in range(line_index, -1, -1):
            match = method_pattern.match(lines[start])
            if match:
                method_name = match.group(1)
                end = self._find_method_end(lines, start)
                if end >= line_index:
                    return method_name, start, end
        return None, max(0, line_index - 10), min(len(lines) - 1, line_index + 10)

    def _classify_inner_html_usage(self, lines: List[str], line_index: int, method_start: int, method_end: int):
        """
        Classify innerHTML usage with lighter severity for trusted admin/legal-content patterns.
        """
        context_start = max(0, method_start)
        context_end = min(len(lines) - 1, method_end)
        context = '\n'.join(lines[context_start:context_end + 1]).lower()

        trusted_content_signals = [
            'getgenericmasterrecords',
            'terms_and_conditions',
            'termspolicy',
            'genericmaster',
            'terms-modal-body',
            'showtoast',
        ]
        if any(signal in context for signal in trusted_content_signals):
            return (
                'Medium',
                'innerHTML used for likely admin-managed legal/metadata content. Prefer lightning-formatted-rich-text or sanitized rendering, and avoid repeated direct DOM writes.'
            )

        return (
            'Critical',
            'Avoid innerHTML Assignment as it can lead to XSS vulnerabilities. Use safe DOM APIs or sanitized rendering.'
        )
    
    def _check_console_logs(self):
        """Check for console.log statements (should not be in production)"""
        if not self.js_code:
            return
        
        console_pattern = re.compile(r'console\.(log|debug|info|warn|error)\s*\(', re.IGNORECASE)
        
        for i, line in enumerate(self.js_code.split('\n'), 1):
            if console_pattern.search(line) and '//' not in line[:line.find('console')]:
                self.issues.append({
                    'file_name': f"{self.component_name}.js",
                    'type': 'LWC',
                    'line_number': i,
                    'category': 'Best Practices',
                    'rule_name': 'Console Statement in Production',
                    'criticality': 'Low',
                    'snippet': line.strip()[:100],
                    'recommendation': 'Remove console statements before deploying to production. Use proper logging.'
                })
    
    def _check_hardcoded_credentials(self):
        """Check for hardcoded credentials or API keys"""
        if not self.js_code:
            return
        
        credential_patterns = [
            (r'password\s*=\s*["\']', 'Hardcoded Password', 'Critical'),
            (r'api[_-]?key\s*=\s*["\']', 'Hardcoded API Key', 'Critical'),
            (r'secret\s*=\s*["\']', 'Hardcoded Secret', 'Critical'),
            (r'token\s*=\s*["\'][^"\']{20,}', 'Hardcoded Token', 'Critical'),
        ]
        
        for i, line in enumerate(self.js_code.split('\n'), 1):
            for pattern, name, criticality in credential_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Skip if it's a comment
                    if '//' in line[:line.lower().find('password')]:
                        continue
                    
                    self.issues.append({
                        'file_name': f"{self.component_name}.js",
                        'type': 'LWC',
                        'line_number': i,
                        'category': 'Security',
                        'rule_name': name,
                        'criticality': criticality,
                        'snippet': '[REDACTED for security]',
                        'recommendation': 'Never hardcode credentials. Use Custom Metadata, Custom Settings, or Named Credentials.'
                    })
    
    def _check_improper_data_binding(self):
        """Check for improper data binding that could lead to XSS"""
        if not self.html_code:
            return
        
        # Check for unescaped data binding with user input
        unsafe_binding_patterns = [
            (r'\{[^}]*\burl\b[^}]*\}', 'Unescaped URL Binding', 'High'),
            (r'\{[^}]*\binput\b[^}]*\}', 'Unescaped User Input', 'High'),
            (r'<script[^>]*>\s*\{', 'Data Binding in Script Tag', 'Critical'),
        ]
        
        for i, line in enumerate(self.html_code.split('\n'), 1):
            for pattern, name, criticality in unsafe_binding_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    self.issues.append({
                        'file_name': f"{self.component_name}.html",
                        'type': 'LWC',
                        'line_number': i,
                        'category': 'Security',
                        'rule_name': name,
                        'criticality': criticality,
                        'snippet': line.strip()[:100],
                        'recommendation': 'Ensure user input is properly escaped. Use Lightning Base Components which auto-escape.'
                    })


def analyze_lwc_component(component_name: str, js_code: str = "", html_code: str = "") -> List[Dict]:
    """
    Analyze an LWC component for issues
    
    Args:
        component_name: Name of the component
        js_code: JavaScript code
        html_code: HTML template
    
    Returns:
        List of issues found
    """
    analyzer = LWCAnalyzer(component_name, js_code, html_code)
    return analyzer.analyze()


if __name__ == "__main__":
    # Test with sample code
    test_html = """
    <template>
        <div class="container">
            <lightning-formatted-text value={userInput} escape={false}></lightning-formatted-text>
        </div>
    </template>
    """
    
    test_js = """
    import { LightningElement } from 'lwc';
    
    export default class TestComponent extends LightningElement {
        handleClick() {
            callApex({ param: 'value' })
                .then(result => {
                    console.log(result);
                });
        }
    }
    """
    
    issues = analyze_lwc_component("testComponent", test_js, test_html)
    print(f"Found {len(issues)} issues:")
    for issue in issues:
        print(f"  - {issue['rule_name']}: {issue['recommendation']}")

