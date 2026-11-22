# Ship a localization handoff

Supply source and target JSON resource maps, a locale, required plural categories, optional glossary entries and optional human-written repairs. A resource is a plain string or a category-to-string plural object. Plural source maps must include `other`. The example German bundle has a dropped player name, an incomplete plural, a glossary mismatch and an obsolete target-only key.

The checker compares named brace placeholders by multiplicity, numbered printf variables by identity, and unnumbered printf arguments by order. It recognizes basic `s`, `d`, `i` and `f` conversions, escaped percent signs and escaped braces. Complex ICU messages and format-specifier syntax are outside this schema. Required plural categories are supplied by the localization team. The checker does not infer them from country codes.

A supplied repair becomes eligible only if it passes the same structural and glossary checks. Approve it to modify the locale JSON. Approve a queue action to add the source text, current translation and issue list to `repair-queue.json` for human translation. Unselected resources and target-only keys remain in the exported bundle. Structural checks cannot establish fluency or quality in context.
