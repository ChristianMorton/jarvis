# Public release preparation

Prepared 9 November 2026. Source remains private; no remote changes were made.

## Changes

- Added a microphone-free command pipeline demonstration and explicit prerequisites.
- Corrected the blanket offline claim: Vosk command recognition is local; optional
  dictation handoff and launched apps have separate network behaviour.
- Documented local speech/configuration privacy and device-verification limits.
- Removed the project-specific example from the configuration template.
- Corrected the partial-results guidance to match the current command loop.
- Made Windows setup stop after a failed native command instead of continuing to
  print a successful completion message.
- Added GitHub Actions for Windows/Linux and Python 3.10/3.12, with read-only
  repository permissions. These remote jobs have not run yet.
- Ignored local environment files and common audio recordings.

## Verification performed

- Installed the editable package and its development dependencies into an isolated
  environment on Windows with Python 3.13.
- `python -m pytest -q --basetemp=.pytest_cache/tmp`: **104 passed**.
  The explicit temporary directory avoids this environment's restricted default
  temporary location; the first run failed during fixture setup for that reason.
- `python -m jarvis test "scroll down" "switch to terminal"`: passed using the
  recording driver, without sending input or opening applications.
- `git diff --check`: passed.
- Windows setup script parses successfully. The full setup flow, model download,
  microphone recognition, startup task and real input delivery were not exercised.

## Source and history review

The original repository contains two commits and 51 distinct historical file blobs.
Both commits' tracked-file snapshots were covered by a scan for private keys,
common provider-token formats, credential-bearing URLs, personal home paths and
private network addresses. No matches were found. Application sources and shipped
configuration were also inspected for network calls and personal configuration.
This is a targeted review, not a guarantee that no sensitive material exists.

The original commit messages contain personal AI session links and author contact
metadata. A clean source archive excludes all Git history. Do not mirror the old
history to a public repository without deciding whether to retain that metadata.
Local microphone recordings and acoustic models are not part of the source.

## Remaining release decisions

- Choose a project licence after confirming ownership. No licence grant was added.
- Confirm third-party dependency and selected acoustic-model licences before
  bundling those assets. The source archive does not bundle them.
- Run the documented device smoke test before advertising measured voice accuracy
  or Windows application compatibility. A short demonstration recording would
  improve the portfolio presentation.
- Create a public GitHub repository from the clean source only when publication
  is explicitly authorised; then verify its Actions jobs.

## Portfolio media added

`docs/media/terminal-demo.png`, `.gif` and `.mp4` present output captured from the
real recording-driver CLI. `terminal-demo.txt` preserves the original text.
`scripts/render-demo.py` reproduces the capture and rendering. Captions explicitly
distinguish simulated input actions from microphone recognition and desktop control.
The three scenes cover parsing, aliases/chaining and wake-word state transitions.
The still was visually inspected; the MP4 was decoded for validation. Voice accuracy
and device behaviour remain unverified. No microphone audio was captured.
