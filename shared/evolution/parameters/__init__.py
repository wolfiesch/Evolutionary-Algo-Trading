"""
Parameter Evolution Schema and Utilities.

This package defines the DNA that gets evolved for Strategy Templates:
- Fixed logic, evolvable parameters
- Vectorized, regime-switched, bidirectional architecture

Usage:
    from shared.evolution.parameters import (
        WeightVector,
        UniversalParameters,
        CryptoParameters,
        ForexParameters,
        validate_parameters,
        repair_constraints,
        discretize_parameters,
    )
"""

from .schema import (
    WeightVector,
    UniversalParameters,
    CryptoParameters,
    ForexParameters,
)

from .validation import (
    validate_parameters,
    repair_constraints,
    clamp_to_bounds,
    UNIVERSAL_CONSTRAINTS,
    CRYPTO_CONSTRAINTS,
    FOREX_CONSTRAINTS,
)

from .discretization import (
    discretize_parameters,
    discretize_weight_vector,
    hash_parameters,
    parameters_are_equivalent,
    calculate_search_space_size,
    DISCRETIZATION_STEPS,
)


__all__ = [
    # Schema
    "WeightVector",
    "UniversalParameters",
    "CryptoParameters",
    "ForexParameters",
    # Validation
    "validate_parameters",
    "repair_constraints",
    "clamp_to_bounds",
    "UNIVERSAL_CONSTRAINTS",
    "CRYPTO_CONSTRAINTS",
    "FOREX_CONSTRAINTS",
    # Discretization
    "discretize_parameters",
    "discretize_weight_vector",
    "hash_parameters",
    "parameters_are_equivalent",
    "calculate_search_space_size",
    "DISCRETIZATION_STEPS",
]
