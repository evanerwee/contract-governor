"""
Property-based tests for field validation utilities.

These tests verify the correctness properties of the field validation
utilities using hypothesis for property-based testing.
"""

from dataclasses import fields
from typing import List, Optional

from hypothesis import given, settings
from hypothesis import strategies as st

from contract_governor.config.field_validator import (
    ParseResult,
    filter_unknown_fields,
    format_unknown_fields_warning,
    get_valid_stipulation_fields,
)
from contract_governor.core.models import ExposurePolicy, StipulationConfig


class TestFieldIntrospection:
    """
    Property 4: Field Validation Uses Dataclass Introspection

    Validates: Requirements 6.3

    For any version of StipulationConfig, the get_valid_stipulation_fields()
    function should return exactly the set of field names defined in the
    StipulationConfig dataclass.
    """

    def test_field_introspection_matches_dataclass_fields(self):
        """
        **Property 4: Field Validation Uses Dataclass Introspection**
        **Validates: Requirements 6.3**

        Verify that get_valid_stipulation_fields() returns exactly the set
        of field names defined in StipulationConfig.
        """
        # Get fields using our utility function
        utility_fields = get_valid_stipulation_fields()

        # Get fields directly from the dataclass
        dataclass_fields = {f.name for f in fields(StipulationConfig)}

        # They should be exactly equal
        assert utility_fields == dataclass_fields, (
            f"Field mismatch: utility returned {utility_fields}, " f"but dataclass has {dataclass_fields}"
        )

    def test_field_introspection_returns_set(self):
        """Verify that get_valid_stipulation_fields() returns a set."""
        result = get_valid_stipulation_fields()
        assert isinstance(result, set), f"Expected set, got {type(result)}"

    def test_field_introspection_non_empty(self):
        """Verify that StipulationConfig has at least one field."""
        result = get_valid_stipulation_fields()
        assert len(result) > 0, "StipulationConfig should have at least one field"

    def test_known_fields_present(self):
        """Verify that known essential fields are present."""
        result = get_valid_stipulation_fields()
        # These are core fields that should always exist
        essential_fields = {
            "exposure_policy",
            "stipulation_id",
            "stipulation_version",
        }
        assert essential_fields.issubset(result), f"Missing essential fields: {essential_fields - result}"


class TestWarningMessageFormat:
    """
    Property 5: Warning Message Format Includes Required Information

    Validates: Requirements 1.1, 1.2

    For any stipulation source path and list of unknown fields, the formatted
    warning message should contain the source path, all unknown field names,
    and the list of valid field names.
    """

    @given(
        source_path=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
        unknown_fields=st.lists(
            st.text(min_size=1, max_size=50).filter(lambda x: x.strip() and "'" not in x), min_size=1, max_size=10
        ),
    )
    @settings(max_examples=100)
    def test_warning_message_contains_source_path(self, source_path: str, unknown_fields: list):
        """
        **Property 5: Warning Message Format Includes Required Information**
        **Validates: Requirements 1.1, 1.2**

        Verify that the warning message contains the source path.
        """
        valid_fields = get_valid_stipulation_fields()
        message = format_unknown_fields_warning(source_path, unknown_fields, valid_fields)

        assert source_path in message, f"Source path '{source_path}' not found in message: {message}"

    @given(
        unknown_fields=st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=97, max_codepoint=122),
                min_size=1,
                max_size=20,
            ),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_warning_message_contains_unknown_fields(self, unknown_fields: list):
        """
        **Property 5: Warning Message Format Includes Required Information**
        **Validates: Requirements 1.1, 1.2**

        Verify that the warning message contains all unknown field names.
        """
        source_path = "/test/path.yaml"
        valid_fields = get_valid_stipulation_fields()
        message = format_unknown_fields_warning(source_path, unknown_fields, valid_fields)

        # Check that each unknown field appears in the message
        for field_name in unknown_fields:
            assert field_name in message, f"Unknown field '{field_name}' not found in message: {message}"

    def test_warning_message_contains_valid_fields(self):
        """
        **Property 5: Warning Message Format Includes Required Information**
        **Validates: Requirements 1.1, 1.2**

        Verify that the warning message contains valid field names.
        """
        source_path = "/test/path.yaml"
        unknown_fields = ["invalid_field"]
        valid_fields = get_valid_stipulation_fields()

        message = format_unknown_fields_warning(source_path, unknown_fields, valid_fields)

        # Check that at least some valid fields appear in the message
        # (they should all be in the sorted list)
        assert "Valid fields are:" in message, f"'Valid fields are:' not found in message: {message}"

        # Check that essential valid fields appear
        for essential_field in ["exposure_policy", "stipulation_id"]:
            assert (
                essential_field in message
            ), f"Essential valid field '{essential_field}' not found in message: {message}"

    def test_warning_message_format_structure(self):
        """Verify the overall structure of the warning message."""
        source_path = "/config/test.yaml"
        unknown_fields = ["bad_field", "another_bad"]
        valid_fields = {"field_a", "field_b", "field_c"}

        message = format_unknown_fields_warning(source_path, unknown_fields, valid_fields)

        # Check structure
        assert "Stipulation at" in message
        assert "contains unsupported fields" in message
        assert "These fields were ignored" in message
        assert "Valid fields are:" in message


# Strategy for generating valid StipulationConfig instances
@st.composite
def valid_stipulation_config(draw):
    """Generate a valid StipulationConfig instance."""
    exposure_policy = draw(st.sampled_from(list(ExposurePolicy)))

    # Generate proxy_prefix_format based on exposure policy
    if exposure_policy == ExposurePolicy.TENANT_SCOPED:
        proxy_prefix = draw(
            st.sampled_from(
                [
                    "/tenant/{tenant_id}/api/v1",
                    "/{scope_id}/service/v2",
                    "/org/{organization_id}/data/v1",
                ]
            )
        )
        requires_scope = True
    else:
        proxy_prefix = draw(
            st.sampled_from(
                [
                    "/api/v1",
                    "/service/v2",
                    None,
                ]
            )
        )
        requires_scope = False

    return StipulationConfig(
        exposure_policy=exposure_policy,
        proxy_prefix_format=proxy_prefix,
        requires_scope_parameter=requires_scope,
    )


# Strategy for generating source paths
source_path_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P"), min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=100,
).filter(lambda x: x.strip() and "/" in x or "." in x)


# Strategy for generating unknown field names
unknown_field_strategy = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=97, max_codepoint=122),
        min_size=1,
        max_size=20,
    ).filter(lambda x: x not in get_valid_stipulation_fields()),
    min_size=0,
    max_size=5,
    unique=True,
)


# Strategy for generating error messages
error_message_strategy = st.one_of(st.none(), st.text(min_size=1, max_size=200).filter(lambda x: x.strip()))


class TestParseResultCorrectness:
    """
    Property 2: ParseResult Correctly Tracks Parsing Outcomes

    Validates: Requirements 2.1, 2.2, 2.3

    For any stipulation source (file path, S3 key, or DynamoDB key):
    - If the source exists and contains valid data with unknown fields, the ParseResult
      should have success=True, source_exists=True, and unknown_fields containing exactly
      the unknown field names
    - If the source exists but contains invalid data, the ParseResult should have
      success=False, source_exists=True, and a non-empty error_message
    - If the source does not exist, the ParseResult should have success=False and
      source_exists=False
    """

    @given(
        config=valid_stipulation_config(),
        source_path=source_path_strategy,
        unknown_fields=unknown_field_strategy,
    )
    @settings(max_examples=100)
    def test_successful_parse_with_unknown_fields(
        self, config: StipulationConfig, source_path: str, unknown_fields: List[str]
    ):
        """
        **Property 2: ParseResult Correctly Tracks Parsing Outcomes**
        **Validates: Requirements 2.1, 2.2, 2.3**

        When a source exists and contains valid data with unknown fields,
        ParseResult should have success=True, source_exists=True, and
        unknown_fields containing exactly the unknown field names.
        """
        result = ParseResult(
            success=True,
            config=config,
            source_path=source_path,
            source_exists=True,
            unknown_fields=unknown_fields,
        )

        # Verify success state
        assert result.success is True
        assert result.source_exists is True
        assert result.config is config
        assert result.source_path == source_path

        # Verify unknown fields tracking
        assert result.unknown_fields == unknown_fields
        assert result.had_unknown_fields == (len(unknown_fields) > 0)

        # Verify valid_fields is populated via __post_init__
        assert result.valid_fields == get_valid_stipulation_fields()

        # Verify no error message for successful parse
        assert result.error_message is None

    @given(
        source_path=source_path_strategy,
        error_message=st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100)
    def test_failed_parse_with_existing_source(self, source_path: str, error_message: str):
        """
        **Property 2: ParseResult Correctly Tracks Parsing Outcomes**
        **Validates: Requirements 2.1, 2.2, 2.3**

        When a source exists but contains invalid data, ParseResult should
        have success=False, source_exists=True, and a non-empty error_message.
        """
        result = ParseResult(
            success=False,
            config=None,
            source_path=source_path,
            source_exists=True,
            error_message=error_message,
        )

        # Verify failure state
        assert result.success is False
        assert result.source_exists is True
        assert result.config is None
        assert result.source_path == source_path

        # Verify error message is present
        assert result.error_message == error_message
        assert len(result.error_message) > 0

        # Verify valid_fields is still populated
        assert result.valid_fields == get_valid_stipulation_fields()

    @given(source_path=source_path_strategy)
    @settings(max_examples=100)
    def test_source_not_found(self, source_path: str):
        """
        **Property 2: ParseResult Correctly Tracks Parsing Outcomes**
        **Validates: Requirements 2.1, 2.2, 2.3**

        When a source does not exist, ParseResult should have success=False
        and source_exists=False.
        """
        result = ParseResult(
            success=False,
            config=None,
            source_path=source_path,
            source_exists=False,
            error_message=f"File not found: {source_path}",
        )

        # Verify not found state
        assert result.success is False
        assert result.source_exists is False
        assert result.config is None
        assert result.source_path == source_path

        # Verify valid_fields is still populated
        assert result.valid_fields == get_valid_stipulation_fields()

    def test_had_unknown_fields_property_true(self):
        """
        **Property 2: ParseResult Correctly Tracks Parsing Outcomes**
        **Validates: Requirements 2.2**

        Verify had_unknown_fields returns True when unknown_fields is non-empty.
        """
        result = ParseResult(
            success=True,
            source_path="/test/path.yaml",
            source_exists=True,
            unknown_fields=["invalid_field", "another_bad_field"],
        )

        assert result.had_unknown_fields is True

    def test_had_unknown_fields_property_false(self):
        """
        **Property 2: ParseResult Correctly Tracks Parsing Outcomes**
        **Validates: Requirements 2.2**

        Verify had_unknown_fields returns False when unknown_fields is empty.
        """
        result = ParseResult(
            success=True,
            source_path="/test/path.yaml",
            source_exists=True,
            unknown_fields=[],
        )

        assert result.had_unknown_fields is False

    def test_valid_fields_auto_populated(self):
        """
        **Property 2: ParseResult Correctly Tracks Parsing Outcomes**
        **Validates: Requirements 2.1**

        Verify valid_fields is automatically populated via __post_init__
        when not explicitly provided.
        """
        result = ParseResult(
            success=True,
            source_path="/test/path.yaml",
            source_exists=True,
        )

        # valid_fields should be auto-populated
        assert result.valid_fields == get_valid_stipulation_fields()
        assert len(result.valid_fields) > 0

    def test_valid_fields_preserved_when_provided(self):
        """
        **Property 2: ParseResult Correctly Tracks Parsing Outcomes**
        **Validates: Requirements 2.1**

        Verify valid_fields is preserved when explicitly provided.
        """
        custom_fields = {"field_a", "field_b"}
        result = ParseResult(
            success=True,
            source_path="/test/path.yaml",
            source_exists=True,
            valid_fields=custom_fields,
        )

        # Custom valid_fields should be preserved
        assert result.valid_fields == custom_fields

    @given(
        success=st.booleans(),
        source_exists=st.booleans(),
        unknown_fields=unknown_field_strategy,
        error_message=error_message_strategy,
    )
    @settings(max_examples=100)
    def test_parse_result_state_consistency(
        self, success: bool, source_exists: bool, unknown_fields: List[str], error_message: Optional[str]
    ):
        """
        **Property 2: ParseResult Correctly Tracks Parsing Outcomes**
        **Validates: Requirements 2.1, 2.2, 2.3**

        Verify ParseResult maintains consistent state across all field combinations.
        """
        result = ParseResult(
            success=success,
            source_path="/test/path.yaml",
            source_exists=source_exists,
            unknown_fields=unknown_fields,
            error_message=error_message,
        )

        # Verify state consistency
        assert result.success == success
        assert result.source_exists == source_exists
        assert result.unknown_fields == unknown_fields
        assert result.error_message == error_message

        # Verify had_unknown_fields is consistent with unknown_fields
        assert result.had_unknown_fields == (len(unknown_fields) > 0)

        # Verify valid_fields is always populated
        assert len(result.valid_fields) > 0


class TestUnknownFieldFilteringPreservesValidConfig:
    """
    Property 1: Unknown Field Filtering Preserves Valid Config

    Validates: Requirements 1.3

    For any valid StipulationConfig data dictionary with additional unknown fields
    added, filtering out the unknown fields and creating a StipulationConfig should
    succeed and produce a config equivalent to one created from the original valid data.
    """

    @given(
        config=valid_stipulation_config(),
        unknown_field_names=st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=97, max_codepoint=122),
                min_size=3,
                max_size=20,
            ).filter(lambda x: x not in get_valid_stipulation_fields()),
            min_size=0,
            max_size=5,
            unique=True,
        ),
        unknown_field_values=st.lists(
            st.one_of(
                st.text(min_size=0, max_size=50),
                st.integers(),
                st.booleans(),
                st.none(),
            ),
            min_size=5,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_filtering_preserves_valid_config_fields(
        self, config: StipulationConfig, unknown_field_names: List[str], unknown_field_values: List
    ):
        """
        **Property 1: Unknown Field Filtering Preserves Valid Config**
        **Validates: Requirements 1.3**

        Verify that filtering unknown fields preserves all valid config fields
        and allows successful StipulationConfig creation.
        """
        # Create a dictionary from the valid config
        valid_data = {
            "exposure_policy": config.exposure_policy,
            "proxy_prefix_format": config.proxy_prefix_format,
            "requires_scope_parameter": config.requires_scope_parameter,
        }

        # Add unknown fields to the data
        data_with_unknown = valid_data.copy()
        for i, field_name in enumerate(unknown_field_names):
            if i < len(unknown_field_values):
                data_with_unknown[field_name] = unknown_field_values[i]

        # Filter unknown fields
        filtered_data, detected_unknown = filter_unknown_fields(data_with_unknown)

        # Verify that all unknown fields were detected
        assert set(detected_unknown) == set(
            unknown_field_names
        ), f"Expected unknown fields {unknown_field_names}, got {detected_unknown}"

        # Verify that valid fields are preserved
        for key in valid_data:
            assert key in filtered_data, f"Valid field '{key}' was incorrectly filtered out"
            assert (
                filtered_data[key] == valid_data[key]
            ), f"Valid field '{key}' value changed: expected {valid_data[key]}, got {filtered_data[key]}"

        # Verify that unknown fields are not in filtered data
        for field_name in unknown_field_names:
            assert field_name not in filtered_data, f"Unknown field '{field_name}' was not filtered out"

        # Verify that a StipulationConfig can be created from filtered data
        new_config = StipulationConfig(**filtered_data)

        # Verify the new config has the same core values
        assert new_config.exposure_policy == config.exposure_policy
        assert new_config.proxy_prefix_format == config.proxy_prefix_format
        assert new_config.requires_scope_parameter == config.requires_scope_parameter

    def test_filtering_empty_dict_returns_empty(self):
        """
        **Property 1: Unknown Field Filtering Preserves Valid Config**
        **Validates: Requirements 1.3**

        Verify that filtering an empty dictionary returns empty results.
        """
        filtered_data, unknown_fields = filter_unknown_fields({})

        assert filtered_data == {}
        assert unknown_fields == []

    def test_filtering_all_valid_fields_returns_all(self):
        """
        **Property 1: Unknown Field Filtering Preserves Valid Config**
        **Validates: Requirements 1.3**

        Verify that filtering data with only valid fields returns all fields.
        """
        valid_data = {
            "exposure_policy": ExposurePolicy.GLOBAL_CONTROL_PLANE,
            "stipulation_id": "test-id",
            "stipulation_version": "1.0.0",
        }

        filtered_data, unknown_fields = filter_unknown_fields(valid_data)

        assert filtered_data == valid_data
        assert unknown_fields == []

    def test_filtering_all_unknown_fields_returns_empty(self):
        """
        **Property 1: Unknown Field Filtering Preserves Valid Config**
        **Validates: Requirements 1.3**

        Verify that filtering data with only unknown fields returns empty data.
        """
        unknown_data = {
            "completely_invalid_field": "value1",
            "another_bad_field": 123,
            "yet_another_unknown": True,
        }

        filtered_data, unknown_fields = filter_unknown_fields(unknown_data)

        assert filtered_data == {}
        assert set(unknown_fields) == set(unknown_data.keys())

    @given(
        valid_field_subset=st.lists(
            st.sampled_from(list(get_valid_stipulation_fields())), min_size=1, max_size=5, unique=True
        ),
    )
    @settings(max_examples=50)
    def test_filtering_preserves_arbitrary_valid_field_subsets(self, valid_field_subset: List[str]):
        """
        **Property 1: Unknown Field Filtering Preserves Valid Config**
        **Validates: Requirements 1.3**

        Verify that any subset of valid fields is preserved after filtering.
        """
        # Create data with the valid field subset
        data = {}
        for field_name in valid_field_subset:
            # Use simple placeholder values
            if field_name == "exposure_policy":
                data[field_name] = ExposurePolicy.GLOBAL_CONTROL_PLANE
            elif field_name in [
                "requires_scope_parameter",
                "inject_metadata",
                "catalog_default_visible",
                "enforce_version_alignment",
            ]:
                data[field_name] = False
            elif field_name in ["forbid_methods", "required_fields"]:
                data[field_name] = []
            elif field_name == "metadata_block":
                data[field_name] = {}
            else:
                data[field_name] = "test_value"

        # Add some unknown fields
        data["unknown_field_1"] = "bad"
        data["unknown_field_2"] = 123

        filtered_data, unknown_fields = filter_unknown_fields(data)

        # Verify all valid fields are preserved
        for field_name in valid_field_subset:
            assert field_name in filtered_data, f"Valid field '{field_name}' was filtered out"

        # Verify unknown fields were detected
        assert "unknown_field_1" in unknown_fields
        assert "unknown_field_2" in unknown_fields


class TestErrorMessageQuality:
    """
    Property 3: Error Messages Distinguish Missing Files from Parse Failures

    Validates: Requirements 3.2, 3.3, 3.4

    For any category:api_major key where no stipulation is loaded:
    - If a stipulation file exists but failed to parse, the error message should
      contain the file path and indicate parsing failed
    - If no stipulation file exists, the error message should indicate no file was found
    - The error messages should be distinguishable from each other
    """

    def test_stipulation_not_found_error_message_format(self):
        """
        **Property 3: Error Messages Distinguish Missing Files from Parse Failures**
        **Validates: Requirements 3.3**

        Verify that StipulationNotFoundError message indicates no file was found.
        """
        from contract_governor.core.errors import StipulationNotFoundError

        category = "test-category"
        api_major = "v1"

        error = StipulationNotFoundError(category=category, api_major_version=api_major)

        message = str(error)

        # Message should indicate no file exists
        assert "No stipulation found" in message
        assert category in message
        assert api_major in message
        assert "No stipulation file exists" in message

    def test_stipulation_parse_error_with_error_message_format(self):
        """
        **Property 3: Error Messages Distinguish Missing Files from Parse Failures**
        **Validates: Requirements 3.2, 3.4**

        Verify that StipulationParseError with error_message indicates parse failure
        and includes the file path.
        """
        from contract_governor.core.errors import StipulationParseError

        category = "test-category"
        api_major = "v1"
        source_path = "/config/stipulations/test-category_v1.yaml"
        parse_error = "Invalid YAML syntax at line 5"

        error = StipulationParseError(
            category=category, api_major_version=api_major, source_path=source_path, parse_error=parse_error
        )

        message = str(error)

        # Message should indicate file exists but failed to parse
        assert "exists" in message.lower()
        assert "failed to parse" in message.lower()
        assert source_path in message
        assert category in message
        assert api_major in message
        assert "Check logs" in message

    def test_stipulation_parse_error_with_unknown_fields_format(self):
        """
        **Property 3: Error Messages Distinguish Missing Files from Parse Failures**
        **Validates: Requirements 3.2, 3.4**

        Verify that StipulationParseError with unknown_fields indicates filtering issue.
        """
        from contract_governor.core.errors import StipulationParseError

        category = "test-category"
        api_major = "v1"
        source_path = "/config/stipulations/test-category_v1.yaml"
        unknown_fields = ["invalid_field", "another_bad_field"]

        error = StipulationParseError(
            category=category, api_major_version=api_major, source_path=source_path, unknown_fields=unknown_fields
        )

        message = str(error)

        # Message should indicate unknown fields were filtered
        assert source_path in message
        assert "unknown fields" in message.lower()
        assert "filtered" in message.lower()
        assert str(unknown_fields) in message

    def test_error_messages_are_distinguishable(self):
        """
        **Property 3: Error Messages Distinguish Missing Files from Parse Failures**
        **Validates: Requirements 3.2, 3.3, 3.4**

        Verify that error messages for missing files vs parse failures are distinguishable.
        """
        from contract_governor.core.errors import StipulationNotFoundError, StipulationParseError

        category = "test-category"
        api_major = "v1"
        source_path = "/config/stipulations/test-category_v1.yaml"

        not_found_error = StipulationNotFoundError(category=category, api_major_version=api_major)

        parse_error = StipulationParseError(
            category=category, api_major_version=api_major, source_path=source_path, parse_error="Invalid syntax"
        )

        not_found_message = str(not_found_error)
        parse_error_message = str(parse_error)

        # Messages should be different
        assert not_found_message != parse_error_message

        # Not found message should indicate no file exists (negative context)
        assert "no stipulation file exists" in not_found_message.lower()

        # Parse error message SHOULD indicate file exists but failed to parse (positive context)
        assert "exists" in parse_error_message.lower() and "but" in parse_error_message.lower()
        assert "failed to parse" in parse_error_message.lower()

        # Parse error should include the source path, not found should not
        assert source_path in parse_error_message
        assert source_path not in not_found_message

    @given(
        category=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=97, max_codepoint=122),
            min_size=1,
            max_size=30,
        ).filter(lambda x: x.strip()),
        api_major=st.sampled_from(["v1", "v2", "v3", "v4", "v5"]),
    )
    @settings(max_examples=100)
    def test_not_found_error_always_contains_key_info(self, category: str, api_major: str):
        """
        **Property 3: Error Messages Distinguish Missing Files from Parse Failures**
        **Validates: Requirements 3.3**

        For any category and api_major, the not found error message should
        always contain the category and version.
        """
        from contract_governor.core.errors import StipulationNotFoundError

        error = StipulationNotFoundError(category=category, api_major_version=api_major)

        message = str(error)

        # Message should always contain category and version
        assert category in message, f"Category '{category}' not in message: {message}"
        assert api_major in message, f"API major '{api_major}' not in message: {message}"

    @given(
        category=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=97, max_codepoint=122),
            min_size=1,
            max_size=30,
        ).filter(lambda x: x.strip()),
        api_major=st.sampled_from(["v1", "v2", "v3", "v4", "v5"]),
        source_path=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P"), min_codepoint=32, max_codepoint=126),
            min_size=5,
            max_size=100,
        ).filter(lambda x: x.strip() and ("/" in x or "." in x)),
        parse_error=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100)
    def test_parse_error_always_contains_path_and_error(
        self, category: str, api_major: str, source_path: str, parse_error: str
    ):
        """
        **Property 3: Error Messages Distinguish Missing Files from Parse Failures**
        **Validates: Requirements 3.2, 3.4**

        For any category, api_major, source_path, and parse_error, the parse error
        message should always contain the source path and indicate parsing failed.
        """
        from contract_governor.core.errors import StipulationParseError

        error = StipulationParseError(
            category=category, api_major_version=api_major, source_path=source_path, parse_error=parse_error
        )

        message = str(error)

        # Message should always contain source path
        assert source_path in message, f"Source path '{source_path}' not in message: {message}"

        # Message should indicate parsing failed
        assert "failed to parse" in message.lower(), f"'failed to parse' not in message: {message}"

    def test_error_http_status_codes(self):
        """
        **Property 3: Error Messages Distinguish Missing Files from Parse Failures**
        **Validates: Requirements 3.2, 3.3**

        Verify that error types have appropriate HTTP status codes.
        """
        from contract_governor.core.errors import StipulationNotFoundError, StipulationParseError

        not_found_error = StipulationNotFoundError(category="test", api_major_version="v1")

        parse_error = StipulationParseError(
            category="test", api_major_version="v1", source_path="/test/path.yaml", parse_error="Invalid syntax"
        )

        # Not found should be 404
        assert not_found_error.get_http_status_code() == 404

        # Parse error should be 422 (Unprocessable Entity)
        assert parse_error.get_http_status_code() == 422

    def test_error_codes_are_distinct(self):
        """
        **Property 3: Error Messages Distinguish Missing Files from Parse Failures**
        **Validates: Requirements 3.2, 3.3**

        Verify that error types have distinct error codes.
        """
        from contract_governor.core.errors import StipulationNotFoundError, StipulationParseError

        not_found_error = StipulationNotFoundError(category="test", api_major_version="v1")

        parse_error = StipulationParseError(
            category="test", api_major_version="v1", source_path="/test/path.yaml", parse_error="Invalid syntax"
        )

        # Error codes should be different
        assert not_found_error.error_code != parse_error.error_code
        assert not_found_error.error_code == "STIPULATION_NOT_FOUND"
        assert parse_error.error_code == "STIPULATION_PARSE_ERROR"
