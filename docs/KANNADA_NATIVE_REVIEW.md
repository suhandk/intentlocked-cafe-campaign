# Kannada and Kanglish native review

Status: **PENDING — no human review or sign-off has occurred.**
Policy: guardian-policy-2.1. Review target: lexicon_kn.py, normalization, approved
surface grammars, and the Kannada/Kanglish tests in test_guardian.py.

Reviewer name: pending. Review date: pending. Reviewed source revision/hash: pending.
Owner approval of campaign facts does not satisfy this language release gate.

- [ ] Check number words, compounds (including ಇಪ್ಪತ್ತೈದು), transliteration variants,
      fractions, half, and percentage terms. Document missing forms and ambiguity.
- [ ] Check weekdays, months, relative dates, and Kanglish spellings including Somavara.
- [ ] Check negation, conditional wrappers, scarcity, free gifts, superlatives,
      eligibility, ID, minimum purchase, and time expressions.
- [ ] Validate positive everyday phrases: ಬನ್ನಿ, ಜೊತೆಯಾಗೋಣ!, approved ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ,
      ಕಾಫಿಗೆ, ಕಾಫಿಯ, ಕಾಫಿಯಲ್ಲಿ, and noun case forms in actual owner-reviewed campaigns.
- [ ] Check that number/script normalization preserves every displayed Kannada code
      point, including ZWJ/ZWNJ; verify highlighted ranges against original strings.
- [ ] Add native adversarial paraphrases and everyday counterexamples to regression tests.
- [ ] Review code-mixed phrases and transliteration variation beyond the current fixtures.
- [ ] Review B3 R4 Kannada/Kanglish hooks, CTAs and channel cadence in
      backend/mock_generation.py and actual live outputs when available. Check
      naturalness of shared-pause, personal-ritual and catch-up strategies; ensure
      local expression does not imply unapproved products, amenities or eligibility.
- [ ] Review the displayed matrix examples in docs/evidence/b3-matrix-*.png.
      Browser rendering and automated Guardian checks are not linguistic approval.
- [ ] Record corrections, unresolved ambiguity, and examples rejected too conservatively.
- [ ] Separately review actual rendered posters when B4 fonts/layout exist.
- [ ] Inspect the B4 full-size PNGs, long-string example and logo layout listed in
      B4_VISUAL_REVIEW.md. Record conjunct/vowel shaping, line-break acceptability,
      font size, naturalness and approved offer forms. Engineering observations
      are separate; no native-reader observations have been supplied yet.

Release decision: **PENDING**. Do not check these boxes based on automated tests,
model output, owner acknowledgment of warnings, or an English-language review.
Independent implementation stages may continue while this gate remains pending.
