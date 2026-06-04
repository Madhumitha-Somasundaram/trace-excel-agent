"""
Transformation Matcher - Maps user requests to PySpark transformations.

Uses pattern matching and LLM to identify the correct transformation.
"""

import re
from typing import Dict, Any, Optional, List
from tools.llm import generate_transformation_code


class TransformationMatcher:
    """
    Matches natural language requests to transformation patterns.
    """

    # Common transformation patterns
    PATTERNS = {
        # Unit conversions
        r"convert.*(?:distance|length).*meters?.*(?:to|into).*kilometers?": {
            "type": "unit_conversion",
            "from_unit": "meters",
            "to_unit": "kilometers",
            "operation": "divide",
            "factor": 1000
        },
        r"convert.*(?:distance|length).*(?:km|kilometers?).*(?:to|into).*miles?": {
            "type": "unit_conversion",
            "from_unit": "kilometers",
            "to_unit": "miles",
            "operation": "multiply",
            "factor": 0.621371
        },
        r"convert.*(?:weight|mass).*(?:kg|kilograms?).*(?:to|into).*(?:lbs?|pounds?)": {
            "type": "unit_conversion",
            "from_unit": "kilograms",
            "to_unit": "pounds",
            "operation": "multiply",
            "factor": 2.20462
        },
        r"convert.*temperature.*(?:celsius|°C).*(?:to|into).*(?:fahrenheit|°F)": {
            "type": "unit_conversion",
            "from_unit": "celsius",
            "to_unit": "fahrenheit",
            "operation": "formula",
            "formula": "(value * 9/5) + 32"
        },

        # Filtering
        r"filter.*(?:where|with|having).*status.*(?:is|equals?|==).*(\w+)": {
            "type": "filter",
            "filter_type": "equality",
            "condition": "status"
        },
        r"filter.*(?:where|with).*(\w+).*(?:greater|more|>).*(?:than)?.*(\d+)": {
            "type": "filter",
            "filter_type": "threshold",
            "operator": ">"
        },
        r"filter.*(?:where|with).*(\w+).*(?:less|fewer|<).*(?:than)?.*(\d+)": {
            "type": "filter",
            "filter_type": "threshold",
            "operator": "<"
        },

        # Aggregations
        r"(?:calculate|compute|find).*(?:average|avg|mean).*(\w+).*(?:by|per|grouped by).*(\w+)": {
            "type": "aggregation",
            "agg_function": "average",
            "group_by": True
        },
        r"(?:calculate|compute|find).*(?:total|sum).*(\w+).*(?:by|per|grouped by).*(\w+)": {
            "type": "aggregation",
            "agg_function": "sum",
            "group_by": True
        },
        r"(?:count|number of).*(?:by|per|grouped by).*(\w+)": {
            "type": "aggregation",
            "agg_function": "count",
            "group_by": True
        },

        # Data cleaning
        r"remove.*duplicates?": {
            "type": "cleaning",
            "operation": "drop_duplicates"
        },
        r"fill.*(?:null|missing|na|empty).*values?": {
            "type": "cleaning",
            "operation": "fill_null"
        },
        r"(?:standardize|normalize|clean).*(?:text|string)": {
            "type": "cleaning",
            "operation": "standardize_text"
        },

        # Date operations
        r"extract.*(?:year|month|day|date).*(?:from|of).*(\w+)": {
            "type": "date_operation",
            "operation": "extract_components"
        },

        # Statistical
        r"(?:rank|ranking|order).*(\w+).*by.*(\w+)": {
            "type": "statistical",
            "operation": "ranking"
        },
        r"(?:moving|rolling).*average.*(\w+)": {
            "type": "statistical",
            "operation": "moving_average"
        },
        r"(?:calculate|compute).*percentage": {
            "type": "statistical",
            "operation": "percentage"
        },
    }

    @classmethod
    def match_transformation(cls, user_request: str) -> Optional[Dict[str, Any]]:
        """
        Match user request to a transformation pattern.

        Args:
            user_request: Natural language transformation request

        Returns:
            Matched pattern metadata or None
        """
        user_request_lower = user_request.lower()

        for pattern, metadata in cls.PATTERNS.items():
            match = re.search(pattern, user_request_lower)
            if match:
                result = metadata.copy()
                result['matched_groups'] = match.groups()
                result['original_request'] = user_request
                return result

        return None

    @classmethod
    def identify_column_names(cls, request: str, available_columns: List[str]) -> List[str]:
        """
        Identify which columns are referenced in the request.

        Args:
            request: User's transformation request
            available_columns: List of available column names

        Returns:
            List of identified column names
        """
        identified = []
        request_lower = request.lower()

        for col in available_columns:
            col_lower = col.lower()

            # Direct mention
            if col_lower in request_lower:
                identified.append(col)
                continue

            # Handle column names with underscores/spaces
            col_variants = [
                col_lower,
                col_lower.replace('_', ' '),
                col_lower.replace(' ', ''),
                ''.join(word[0] for word in col_lower.split('_'))  # Acronym
            ]

            if any(variant in request_lower for variant in col_variants):
                identified.append(col)

        return identified

    @classmethod
    def extract_numeric_value(cls, text: str) -> Optional[float]:
        """
        Extract numeric value from text.

        Examples:
            "greater than 1000" -> 1000.0
            "more than 5.5" -> 5.5
        """
        match = re.search(r'\b(\d+\.?\d*)\b', text)
        if match:
            return float(match.group(1))
        return None

    @classmethod
    def build_transformation_request(
        cls,
        user_request: str,
        columns: List[str],
        sample_data: Dict[str, list]
    ) -> Dict[str, Any]:
        """
        Build a complete transformation request from user input.

        This combines pattern matching with LLM understanding.

        Args:
            user_request: Natural language request
            columns: Available columns
            sample_data: Sample data for context

        Returns:
            Transformation specification
        """

        # Step 1: Pattern matching
        pattern_match = cls.match_transformation(user_request)

        # Step 2: Identify referenced columns
        referenced_cols = cls.identify_column_names(user_request, columns)

        # Step 3: Extract numeric values if any
        numeric_value = cls.extract_numeric_value(user_request)

        transformation_spec = {
            "user_request": user_request,
            "pattern_match": pattern_match,
            "referenced_columns": referenced_cols,
            "numeric_value": numeric_value,
            "transformation_type": pattern_match.get("type") if pattern_match else "custom"
        }

        # Step 4: Use LLM for complex or ambiguous requests
        if not pattern_match or len(referenced_cols) == 0:
            # Fall back to LLM
            llm_result = generate_transformation_code(user_request, columns, sample_data)
            transformation_spec["llm_generated"] = True
            transformation_spec["code"] = llm_result.get("code", "")
            transformation_spec["explanation"] = llm_result.get("explanation", "")
        else:
            transformation_spec["llm_generated"] = False

        return transformation_spec


# Example usage and testing
if __name__ == "__main__":
    # Test pattern matching
    test_requests = [
        "Convert distance from meters to kilometers",
        "Filter rows where status is active",
        "Calculate average salary by department",
        "Remove duplicate entries",
        "Extract year from order_date"
    ]

    matcher = TransformationMatcher()

    for request in test_requests:
        result = matcher.match_transformation(request)
        print(f"\nRequest: {request}")
        print(f"Match: {result}")
