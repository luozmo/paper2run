# Review resolution

- Spec P2: report and comparison missing items, and report/inspection/comparison warnings explicitly carry `未提供证据` in both exported formats. No evidence associations are inferred.
- Accepted standards suggestion: three private text/code/table block types replace the implicit tuple protocol; the section and Markdown annotations now describe the actual returned blocks. Public render interface is unchanged.
- Regression verification uses the agreed `PaperReportRenderer.render` seam and reopens both outputs. Red: 11 passed, 1 failed before the marker change. Green after fixes/refactoring: full project suite 28 passed.
- Native Word all-page visual QA is handled by the integration reviewer separately.
