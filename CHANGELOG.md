## v2.2.0 (2025-12-12)

### Feat

- **cache**: add cache utilities and tests

## v2.1.0 (2025-12-01)

### Feat

- **version**: add version retrieval from package metadata

## v2.0.0 (2025-11-27)

### BREAKING CHANGE

- Node.inti_call() has been replaced by initialize_and_call();
use the new name or rely on the deprecated wrapper.

### Feat

- **lib**: add descriptive shelf exceptions and docs
- **lib**: add support for external shelves with weak references

### Fix

- **tests**: update assertion in test_in_node_test_varaset to check for prefix in BASE_CONFIG_DIR
- **logging**: use deepcopy for handler configuration to prevent mutation
- **lib**: register nodes for external shelves
- **tests**: refine assertion thresholds in test_triggerspeeds for improved accuracy
- **tests**: adjust assertion threshold in test_triggerspeeds for better accuracy
- **utils**: improve error handling in write_json_secure function
- **triggerstack**: import pytest_funcnodes conditionally to avoid circular imports
- **core**: harden config and util behavior with regression tests
- **config**: align deprecated test helpers with pytest and move testing to pytest-funcnodes
- **node**: correct UUID uniqueness check for IO objects
- **node**: improve UUID generation for IO objects to prevent duplicates
- **config**: ensure config directory paths are absolute

### Refactor

- **config**: use deepcopy for DEFAULT_CONFIG to prevent mutation
- **core**: adopt pytest-funcnodes and rename node init helper
- **config, testing**: migrate configuration and testing setup to pytest
- **tests**: migrate test cases from unittest to pytest with async support
- **lib**: enhance external shelf management and child retrieval
- **tests**: migrate TestTriggerSpeed from unittest to pytest
- **lib**: flatten shelf store and rename serializer

## v1.0.5 (2025-09-16)

### Feat

- add include_on parameter to to_dict methods for NodeInput and NodeOutput, to allow setting of "on" via the Annotated typing format.

## v0.4.1 (2025-06-05)

### Fix

- enhance done method in DataPath to handle None breaking_nodes and improve clarity

## v0.4.0 (2025-06-05)

### Feat

- enhance DataPath with string representation and graph methods
- implement DataPath class and integrate with NodeIO for enhanced data flow management

### Fix

- improve string representation in src_repr method for better clarity

## v0.3.26 (2025-02-12)

## v0.3.25 (2025-02-11)

## v0.3.24 (2025-02-11)

## v0.3.23 (2025-02-11)

## v0.3.22 (2025-02-10)

## v0.3.21 (2025-02-09)

## v0.3.20 (2025-02-08)

## v0.3.19 (2025-02-05)

## v0.3.18 (2025-02-04)

## v0.3.17 (2025-02-04)

## v0.3.16 (2025-01-28)

## v0.3.15 (2025-01-28)

## v0.3.14 (2025-01-21)

## v0.3.13 (2025-01-20)

## v0.3.12 (2025-01-20)

## v0.3.11 (2025-01-20)

## v0.3.10 (2025-01-16)

## v0.3.9 (2025-01-12)

## v0.3.8 (2025-01-09)

## v0.3.7 (2025-01-09)

## v0.3.6 (2024-12-13)

## v0.3.5 (2024-12-13)

## v0.3.4 (2024-12-13)

## v0.3.3 (2024-12-12)

## v0.3.2 (2024-12-09)

## v0.3.1 (2024-12-09)

## v0.3 (2024-12-09)

## v0.2.4 (2024-12-05)

## v0.2.3 (2024-11-11)

## v0.2.2 (2024-11-07)

## v0.2.1 (2024-11-07)

## v0.2.0 (2024-10-23)

## v0.1.27 (2024-10-22)

## v0.1.26 (2024-10-19)

## v0.1.25 (2024-10-19)

## v0.1.24 (2024-10-18)

## v0.1.23 (2024-10-08)

## v0.1.22 (2024-10-08)

## v0.1.21 (2024-10-08)

## v0.1.20 (2024-10-07)

## v0.1.19 (2024-09-30)

## v0.1.18 (2024-09-27)

## v0.1.17 (2024-09-27)

## v0.1.16 (2024-09-26)

## v0.1.15 (2024-09-25)

## v0.1.14 (2024-09-24)

## v0.1.13 (2024-09-24)

## v0.1.12 (2024-09-23)

## v0.1.11 (2024-09-23)

## v0.1.10 (2024-09-13)

## v0.1.9 (2024-09-04)

## v0.1.8 (2024-09-03)

## v0.1.7 (2024-09-03)

## v0.1.6 (2024-09-03)

## v0.1.5 (2024-09-03)

## v0.1.4 (2024-08-31)

## v0.1.3 (2024-08-30)

## v0.1.2 (2024-08-29)

## v0.1.1 (2024-08-28)

## v0.1.0 (2024-08-28)
