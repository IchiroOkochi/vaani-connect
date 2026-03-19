Update the root `CHANGELOG.md` for this repository.

Requirements:
- Edit only `CHANGELOG.md`.
- Use the existing format and keep older entries intact.
- Base the entry on the current uncommitted repo changes, excluding `CHANGELOG.md` itself.
- Inspect the relevant diffs or files before writing.
- If the latest entry already covers today's work, update that top entry instead of adding a duplicate date block.
- Keep the summary concrete and specific to the changed code.
- Mention changed files in the `Files:` line.
- Include `Commands Run:` and `Validation:` only if you can determine them from the repo state; otherwise write `None`.
- Do not invent test results, commands, or next steps.
- Do not mention this automation, the watcher, or Codex.

Return after the changelog file has been updated.
