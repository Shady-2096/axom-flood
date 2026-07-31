"""Credential-gated rainfall source adapters."""

from .imd import ImdAccessRestrictedError, ImdClient, SourceDisabledError
from .imerg import (
    IMERG_POLICIES,
    ImergCellAccumulation,
    ImergGridCellObservation,
    ImergRun,
    accumulate_imerg_cell,
    parse_imerg_observations,
    prepare_imerg_zonal_join,
)
from .provenance import (
    GeometryReference,
    GeometryReviewRequired,
    SourceRevision,
    write_immutable_revision,
)

__all__ = [
    "IMERG_POLICIES",
    "GeometryReference",
    "GeometryReviewRequired",
    "ImdAccessRestrictedError",
    "ImdClient",
    "ImergCellAccumulation",
    "ImergGridCellObservation",
    "ImergRun",
    "SourceDisabledError",
    "SourceRevision",
    "accumulate_imerg_cell",
    "parse_imerg_observations",
    "prepare_imerg_zonal_join",
    "write_immutable_revision",
]
