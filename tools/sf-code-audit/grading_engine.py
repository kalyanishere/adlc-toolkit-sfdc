"""
Grading Engine Module for Salesforce Code Audit
Implements the scoring and grading system based on audit results
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum


class Grade(Enum):
    """Code health grades"""
    EXCELLENT = "Excellent"
    VERY_GOOD = "Very Good"
    GOOD = "Good"
    AVERAGE = "Average"
    BELOW_AVERAGE = "Below Average"
    POOR = "Poor"


class Criticality(Enum):
    """Issue criticality levels"""
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class IssueCounts:
    """Counts of issues by criticality"""
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    
    def total(self) -> int:
        """Get total issue count"""
        return self.critical + self.high + self.medium + self.low


@dataclass
class CoverageStats:
    """Test coverage statistics"""
    org_coverage: float
    classes_below_90: int
    classes_below_75: int
    total_classes: int
    average_class_coverage: float


@dataclass
class GradingResult:
    """Result of grading analysis"""
    grade: Grade
    issue_counts: IssueCounts
    coverage_stats: CoverageStats
    grade_rationale: str
    top_priority_fixes: List[Dict]
    executive_summary: str


class GradingEngine:
    """
    Implements the grading logic based on the audit specification
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize grading engine with configuration
        
        Args:
            config: Configuration dictionary from config.yaml
        """
        self.config = config or self._default_config()
    
    def _default_config(self) -> Dict:
        """Default grading configuration"""
        return {
            'excellent': {
                'critical': 0,
                'high': 0,
                'medium_max': 14,
                'org_coverage_min': 90
            },
            'very_good': {
                'critical': 0,
                'high_max': 9,
                'medium_max': 29,
                'org_coverage_min': 85
            },
            'good': {
                'critical_max': 3,
                'high_max': 14,
                'org_coverage_min': 75
            },
            'average': {
                'critical_max': 5,
                'high_max': 49,
                'org_coverage_min': 70
            },
            'below_average': {
                'critical_max': 10,
                'org_coverage_min': 50
            },
            'poor': {
                'critical_min': 10,
                'org_coverage_max': 50
            }
        }
    
    def calculate_grade(
        self,
        issue_counts: IssueCounts,
        coverage_stats: CoverageStats,
        has_soql_dml_in_loops: bool = False
    ) -> GradingResult:
        """
        Calculate overall code health grade
        
        Args:
            issue_counts: Count of issues by criticality
            coverage_stats: Test coverage statistics
            has_soql_dml_in_loops: Whether SOQL/DML in loops were found
        
        Returns:
            GradingResult with grade and details
        """
        # Determine grade using the waterfall logic
        grade, rationale = self._determine_grade(
            issue_counts,
            coverage_stats,
            has_soql_dml_in_loops
        )
        
        # Generate executive summary
        executive_summary = self._generate_executive_summary(
            grade,
            issue_counts,
            coverage_stats,
            has_soql_dml_in_loops
        )
        
        result = GradingResult(
            grade=grade,
            issue_counts=issue_counts,
            coverage_stats=coverage_stats,
            grade_rationale=rationale,
            top_priority_fixes=[],  # To be populated by caller
            executive_summary=executive_summary
        )
        
        return result
    
    def _determine_grade(
        self,
        issues: IssueCounts,
        coverage: CoverageStats,
        has_loops: bool
    ) -> Tuple[Grade, str]:
        """
        Determine grade using waterfall logic (assign lowest grade triggered)
        
        Returns:
            Tuple of (Grade, rationale string)
        """
        # POOR triggers (most severe)
        if has_loops:
            return (
                Grade.POOR,
                "Severe: SOQL/DML in loops detected, which falls into the Poor grade band"
            )
        
        if coverage.org_coverage < 50:
            return (
                Grade.POOR,
                f"Severe: Org coverage is {coverage.org_coverage:.1f}% (below 50%), poses significant deployment risk"
            )
        
        if issues.critical >= 10:
            return (
                Grade.POOR,
                f"Severe: {issues.critical} Critical issues found (10+), major refactoring required"
            )
        
        # EXCELLENT
        if (coverage.org_coverage >= 90 and
            issues.critical == 0 and
            issues.high == 0 and
            issues.medium < 15):
            return (
                Grade.EXCELLENT,
                f"No Critical or High issues, {issues.medium} Medium issues, and {coverage.org_coverage:.1f}% coverage"
            )
        
        # VERY GOOD
        if (coverage.org_coverage >= 85 and
            issues.critical == 0 and
            issues.high < 10 and
            issues.medium < 30):
            return (
                Grade.VERY_GOOD,
                f"0 Critical issues, {issues.high} High issues, {issues.medium} Medium issues, and {coverage.org_coverage:.1f}% coverage"
            )
        
        # GOOD
        if (coverage.org_coverage >= 75 and
            issues.critical <= 3 and
            issues.high < 15):
            return (
                Grade.GOOD,
                f"{issues.critical} Critical issues, {issues.high} High issues, and {coverage.org_coverage:.1f}% coverage meet the Good band"
            )
        
        # AVERAGE triggers
        if (coverage.org_coverage >= 70 and
            issues.critical <= 5 and
            issues.high < 50):
            return (
                Grade.AVERAGE,
                f"{issues.critical} Critical issues, {issues.high} High issues, and {coverage.org_coverage:.1f}% coverage place this in the Average band"
            )
        
        # BELOW AVERAGE
        if (coverage.org_coverage >= 50 and
            issues.critical <= 10):
            return (
                Grade.BELOW_AVERAGE,
                f"{issues.critical} Critical issues and {coverage.org_coverage:.1f}% coverage place this in the Below Average band"
            )
        
        # Default to POOR if minimum thresholds are not met
        return (
            Grade.POOR,
            f"Does not meet minimum thresholds: {issues.critical} Critical issues, {issues.high} High issues, {coverage.org_coverage:.1f}% coverage"
        )
    
    def _generate_executive_summary(
        self,
        grade: Grade,
        issues: IssueCounts,
        coverage: CoverageStats,
        has_loops: bool
    ) -> str:
        """Generate executive summary paragraph"""
        
        # Grade-specific opening
        grade_openings = {
            Grade.EXCELLENT: "The codebase demonstrates exceptional quality with strong adherence to best practices.",
            Grade.VERY_GOOD: "The codebase shows very good overall quality with minor areas for improvement.",
            Grade.GOOD: "The codebase demonstrates good quality with some areas requiring attention.",
            Grade.AVERAGE: "The codebase meets basic standards but has notable issues requiring immediate attention.",
            Grade.BELOW_AVERAGE: "The codebase has significant quality issues that pose risks to stability and performance.",
            Grade.POOR: "The codebase has severe quality issues with critical defects that pose imminent risks to production stability, security, and maintainability. Major refactoring is urgently required."
        }
        
        summary_parts = [grade_openings[grade]]
        
        # Security assessment
        if issues.critical > 0:
            summary_parts.append(
                f"Security and performance concerns are present with {issues.critical} Critical "
                f"issue(s) requiring immediate remediation."
            )
        else:
            summary_parts.append(
                "No critical security or performance vulnerabilities were identified."
            )
        
        # Coverage assessment
        if coverage.org_coverage >= 90:
            summary_parts.append(
                f"Test coverage is excellent at {coverage.org_coverage:.1f}%, "
                "demonstrating strong quality assurance practices."
            )
        elif coverage.org_coverage >= 85:
            summary_parts.append(
                f"Test coverage is very good at {coverage.org_coverage:.1f}%, "
                "providing strong assurance with room for incremental improvement."
            )
        elif coverage.org_coverage >= 75:
            summary_parts.append(
                f"Test coverage at {coverage.org_coverage:.1f}% supports the Good grade band "
                "but should be improved further."
            )
        elif coverage.org_coverage >= 70:
            summary_parts.append(
                f"Test coverage at {coverage.org_coverage:.1f}% is only in the Average band "
                "and should be improved for stronger quality assurance."
            )
        else:
            summary_parts.append(
                f"Test coverage at {coverage.org_coverage:.1f}% is below acceptable standards "
                "and represents a significant risk."
            )
        
        # Governor limits
        if has_loops:
            summary_parts.append(
                "CRITICAL: SOQL/DML operations in loops were detected, which can cause "
                "governor limit exceptions in production. This must be addressed immediately."
            )
        
        # Maintainability
        if issues.high >= 15:
            summary_parts.append(
                f"Maintainability concerns exist with {issues.high} High priority issues "
                "that should be addressed to prevent technical debt accumulation."
            )
        elif issues.high > 0:
            summary_parts.append(
                f"Minor maintainability improvements are recommended to address {issues.high} "
                "High priority issue(s)."
            )
        
        # Medium issues
        if issues.medium > 20:
            summary_parts.append(
                f"Additionally, {issues.medium} Medium priority issues were identified "
                "that should be addressed in upcoming development cycles."
            )
        
        return " ".join(summary_parts)
    
    def categorize_criticality(
        self,
        rule_name: str,
        category: str,
        has_coverage_below_90: bool = False
    ) -> Criticality:
        """
        Determine criticality level based on rule name and category
        
        Args:
            rule_name: Name of the rule violated
            category: Category (Security, Performance, etc.)
            has_coverage_below_90: Whether class has <90% coverage
        
        Returns:
            Criticality level
        """
        # Critical: Security and Performance
        critical_rules = [
            'ApexCRUDViolation',
            'ApexSharingViolations',
            'ApexSOQLInjection',
            'ApexBadCrypto',
            'ApexInsecureEndpoint',
            'ApexXSSFromEscapeFalse',
            'ApexXSSFromURLParam',
            'AvoidNonRestrictiveQueries',
            'EagerlyLoadedDescribeSObjectResult',
            'OperationWithHighCostInLoop',
            'OperationWithLimitsInLoop',
            'SOQL_IN_LOOP',
            'DML_IN_LOOP',
            'INDIRECT_SOQL',
            'INDIRECT_DML'
        ]
        
        if rule_name in critical_rules or category == 'Security' or category == 'Performance':
            return Criticality.CRITICAL
        
        # High: Major issues
        high_rules = [
            'ApexUnitTestClassShouldHaveRunAs',
            'AvoidHardcodingId',
            'EventBusWithoutCallback',
            'FutureMethod',
            'AsyncInTrigger',
            'DuplicateFields',
            'FlowIssues',
            'DoubleClickPrevention'
        ]
        
        if rule_name in high_rules or has_coverage_below_90:
            return Criticality.HIGH
        
        # Medium: Best practices and design
        if category in ['BestPractices', 'Design', 'ErrorProne', 'DataModel']:
            return Criticality.MEDIUM
        
        # Default to Low
        return Criticality.LOW
    
    def generate_priority_fixes(
        self,
        all_issues: List[Dict],
        top_n: int = 5
    ) -> List[Dict]:
        """
        Generate top priority fixes aggregated by rule type with counts
        
        Args:
            all_issues: List of all issues found
            top_n: Number of top fixes to return
        
        Returns:
            List of top priority fixes with aggregated counts
        """
        # Group issues by rule name and criticality
        rule_groups = {}
        
        for issue in all_issues:
            rule_name = issue.get('rule_name', 'Unknown')
            criticality = issue.get('criticality', 'Unknown')
            key = f"{rule_name}|{criticality}"
            
            if key not in rule_groups:
                rule_groups[key] = {
                    'rule': rule_name,
                    'criticality': criticality,
                    'count': 0,
                    'category': issue.get('category', 'Unknown'),
                    'recommendation': issue.get('recommendation', 'Review and fix'),
                    'files': []
                }
            
            rule_groups[key]['count'] += 1
            if len(rule_groups[key]['files']) < 3:  # Keep top 3 file examples
                rule_groups[key]['files'].append(issue.get('file_name', 'Unknown'))
        
        # Sort by criticality and count
        criticality_order = {
            'Critical': 0,
            'High': 1,
            'Medium': 2,
            'Low': 3
        }
        
        sorted_groups = sorted(
            rule_groups.values(),
            key=lambda x: (
                criticality_order.get(x['criticality'], 99),
                -x['count']  # Higher count first within same criticality
            )
        )
        
        # Take top N
        top_fixes = []
        for group in sorted_groups[:top_n]:
            file_examples = ', '.join(group['files'][:3])
            if len(group['files']) > 3:
                file_examples += f" (+{len(group['files']) - 3} more)"
            
            top_fixes.append({
                'rule': f"{group['rule']} ({group['count']} instances)",
                'file': file_examples,
                'line': 'Multiple',
                'criticality': group['criticality'],
                'recommendation': group['recommendation'],
                'count': group['count']
            })
        
        return top_fixes
    
    def generate_issue_pivot(
        self,
        all_issues: List[Dict]
    ) -> Dict[str, Dict[str, int]]:
        """
        Generate pivot table of issues by category and criticality
        
        Args:
            all_issues: List of all issues
        
        Returns:
            Dictionary with category -> criticality -> count
        """
        pivot = {}
        
        for issue in all_issues:
            category = issue.get('category', 'Other')
            criticality = issue.get('criticality', 'Low')
            
            if category not in pivot:
                pivot[category] = {
                    'Critical': 0,
                    'High': 0,
                    'Medium': 0,
                    'Low': 0
                }
            
            pivot[category][criticality] = pivot[category].get(criticality, 0) + 1
        
        return pivot


def example_usage():
    """Example usage of the grading engine"""
    
    # Sample data
    issues = IssueCounts(
        critical=0,
        high=3,
        medium=15,
        low=8
    )
    
    coverage = CoverageStats(
        org_coverage=87.5,
        classes_below_90=12,
        classes_below_75=3,
        total_classes=45,
        average_class_coverage=85.2
    )
    
    # Create grading engine
    engine = GradingEngine()
    
    # Calculate grade
    result = engine.calculate_grade(
        issue_counts=issues,
        coverage_stats=coverage,
        has_soql_dml_in_loops=False
    )
    
    print(f"Grade: {result.grade.value}")
    print(f"Rationale: {result.grade_rationale}")
    print(f"\nExecutive Summary:")
    print(result.executive_summary)
    print(f"\nIssue Counts:")
    print(f"  Critical: {issues.critical}")
    print(f"  High: {issues.high}")
    print(f"  Medium: {issues.medium}")
    print(f"  Low: {issues.low}")


if __name__ == "__main__":
    example_usage()

