# Provider Data Domain Glossary

## Provider Directory

A list of providers and locations shown to patients, payers, call centers, referral teams, and internal operations staff. It may include name, specialty, NPI, address, phone, network status, accepting-new-patients status, and last verification date.

## NPI

National Provider Identifier. A standard identifier for healthcare providers in the United States. NPI is a high-value matching field, but it is not sufficient by itself because one provider can practice at multiple locations and source systems can disagree.

## Provider Roster

An internal or external list of providers. Roster files are often exchanged as CSV or Excel exports between operations teams, payers, practices, and vendors.

## Directory Accuracy

The degree to which provider directory information reflects reality. Important fields include address, phone, specialty, location, network status, and accepting-new-patients status.

## Data Validation

Checking whether fields are present, correctly formatted, consistent, and usable. This project validates required fields, phone length, verification dates, and status values.

## Exception Report

A list of records that failed one or more rules and need review. It gives operations staff a concrete queue of records to investigate.

## Duplicate Candidate

Two or more records that may represent the same provider/location. They should not be automatically merged without review.

## Entity Resolution

The process of deciding whether records from different sources represent the same real-world provider, location, organization, or provider-location relationship.

## Source of Truth

The system or dataset treated as authoritative for a given decision. A mature workflow may use different sources of truth for different fields.

## Truth Layer

A curated layer above raw source files. It stores normalized, reviewed, confidence-scored, or exception-aware records that downstream systems can trust more than raw exports.

## Stale Verification

A record that has not been checked recently enough to be trusted for operational or patient-facing use. The threshold depends on policy; the sample configuration uses 365 days.

## Accepting New Patients

Whether a provider is taking new patients. This can vary by location, payer, specialty, or appointment type and should not be inferred from stale data.

## Network Status

Whether a provider participates in a payer network or product. This is important for payer directories and patient access.

## Human Review Queue

A workflow where uncertain or high-risk records are assigned to staff. Ambiguous data should not be silently corrected.

## Audit Trail

Evidence of what changed, when, why, and by whom. This matters when data supports patient-facing or compliance-sensitive workflows.

## KPI

Key performance indicator. Relevant measures include issue rate, stale record count, duplicate candidate count, missing phone count, and issue count by source.

## Operational Follow-Up

The process after an issue is found: contact the source owner, verify the value, update the source system, document resolution, and monitor recurrence.
