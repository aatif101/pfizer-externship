# SDF Field Definitions — Shared Labeling Rulebook

This document is the **single source of truth** for how the six Pfizer SDF
compliance fields are labeled. It governs **both**:

1. The extraction prompts (`src/extraction/gemini.py` — text and visual prompts), and
2. The gold labels (`gold_extraction_labels`, maintained via
   `scripts/relabel_gold_field_rules.py`).

Prompts and gold labels MUST agree with the conventions below. A field is scored
against the gold label, so a prompt that diverges from this rulebook will be
penalized even when the model is "right" by some other standard.

## Scope

Supplier SDF PDFs are frequently **packets**: emails, handwritten notes, template
pages, processing records, SDS pages, and multiple supporting certificates bundled
into one document. Always identify the **primary product/material certificate**
(Certificate of Analysis, Certificate of Quality, Certificate of Compliance, or
equivalent) and extract all six fields from that primary sub-document only.
Section ownership follows strong document headings across page boundaries: a
continuation page inherits the preceding certificate until another strong heading
(for example an email cover, SDS, processing/dosimetry certificate, template, or
calibration report) closes that scope. A prose mention of an attached certificate
or specification is not a heading and cannot reopen primary scope.

## The Six Fields

### `doc_type`
The document/certificate type of the primary sub-document, as printed (e.g.
"Certificate of Analysis", "Certificate of Compliance", "Supplier Declaration Form").

### `vendor_name`
The **full legal name** of the supplier/vendor **as printed** on the primary
certificate. Never abbreviate and never expand beyond what is printed.

- Use "Colder Products Company", not the abbreviation "CPC".
- Use the complete legal entity name exactly as it appears.
- Reject product/material/trade names, lot or batch values, and approver/signatory
  names. Accept an explicit vendor/supplier/manufacturer/"Issued By" value, a
  corporate identity in supplier context, or a review-forced image/logo claim as
  described by the grounding contract below.

### `manufacturing_date`
The manufacturing / production date of the material on the primary certificate.

### `effective_date`
The date the certificate/declaration becomes effective on the primary certificate.

**Synonyms accepted** — on the primary certificate, `effective_date` may be sourced
from any of these printed labels:

- "Approved On"
- "Issue Date"
- "Date of Issue"

(e.g. "Approved On: 22MAY2025" → `effective_date` = 2025-05-22.)

### `revision_date`
The revision / last-revised date of the primary certificate, as printed.

### `expiry_date`
The expiry / expiration date of the primary certificate.

- If expiry is **printed as "N/A"** (or an equivalent printed not-applicable marker),
  extract the **literal string value `"N/A"`** — do **not** abstain. A printed "N/A"
  is a real, asserted value meaning "no expiry".

## Trap-Date Exclusions (always enforced)

These exclusions hold for **all** fields, prompts, and gold labels. They are NOT
weakened by the synonym/N/A rules above:

- **Delivery Date ≠ `effective_date`.** Never map a Delivery Date to effective_date.
- **Retest Date ≠ `expiry_date`.** Never map a Retest Date to expiry_date.
- Never use **email dates**, **handwritten notes**, **template release dates**,
  **SDS page dates**, **processing-record dates**, or **unrelated attachment dates**
  as values for the six fields unless the exact target field is explicitly present
  on the primary product/material certificate.

## Grounding Contract

- **Text-grounded (`evidence_type='text'`):** when a cited page has stored text, the
  `verbatim_span` MUST appear verbatim in that page text, or the field abstains.
- **Visual-grounded (`evidence_type='visual'`):** when a cited page's stored text is
  EMPTY (scanned pages where verbatim text grounding is impossible), an
  image-grounded value is accepted with the page citation preserved and
  `needs_review` forced on. One deliberately narrow mixed-content exception exists
  for `vendor_name`: a supplier logo/header omitted by OCR may be accepted from an
  image-backed primary page only when the visual provider supplies a finite,
  positive `x/y/width/height` region. It remains visual evidence and always requires
  review. All other failed span matches against **non-empty** page text abstain.
