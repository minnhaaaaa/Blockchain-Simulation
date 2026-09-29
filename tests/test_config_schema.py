import tempfile
import unittest
from pathlib import Path

from agentguard.config import ConfigError, SignallingConfig
from agentguard.schema_validation import SchemaValidationError, SchemaValidator


ROOT=Path(__file__).resolve().parents[1]


class ConfigSchemaTests(unittest.TestCase):
    def test_missing_configuration_fails(self):
        with self.assertRaises(ConfigError): SignallingConfig.from_mapping({})
    def test_unknown_contract_fields_fail(self):
        validator=SchemaValidator(ROOT/"contracts"/"schemas")
        with self.assertRaises(SchemaValidationError):
            validator.validate_named("room-join.schema.json",{"schema_version":1,"unexpected":"data"})
