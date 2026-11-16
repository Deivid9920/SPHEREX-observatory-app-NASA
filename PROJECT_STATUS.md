# Project Status — SPHEREx Temporal Observatory

**Current version:** `v0.5.0-rc.1`  
**Development status:** Research prototype / Release Candidate  
**Last updated:** November 15, 2026

## Project maturity

SPHEREx Temporal Observatory is a functional research-oriented software prototype for exploring and processing SPHEREx astronomical data.

The project has completed an initial integration and scientific validation cycle, including real FITS data management, spectral calibration integration, WCS checks, and complementary astrometric validation.

## Verified capabilities

- Local FITS inventory and SHA-256 integrity tracking.
- FITS metadata and HDU inspection.
- Astronomical image preview generation.
- Celestial WCS coordinate transformations.
- Spectral WCS calibration integration for D1 and D2.
- Local spectral extraction workflow.
- Complementary Gaia DR3 astrometric validation.
- Backend and frontend integration.

## Current scientific limitations

- Temporal transient detection is not scientifically validated.
- Three MEF products remain astrometrically unvalidated.
- Absolute photometric validation is pending.
- Discovery and object-detection capabilities remain experimental or incomplete.
- Production persistence configurations require additional validation.

## Validation philosophy

The project uses explicit validation states to distinguish successful tests from partial validation, blocked workflows, and untested capabilities.

A successful software test is not automatically considered scientific validation.

## Current objective

The immediate objective is to consolidate the existing implementation, preserve the evidence generated during development, improve reproducibility, and establish a transparent baseline for future scientific validation.
