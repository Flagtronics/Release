# Flagtronics Release

Shipping artifacts for Flagtronics products: firmware images,
software installers, track maps, and their release notes. Each
component's `current/` directory holds exactly what a user receives —
the binary, its `version.txt`, and its `releasenotes.txt` — and those
three move together in one release commit.

## Release tagging standard

Every release commit on `main` carries an annotated git tag, named by
component. Create the tag on the release commit and push it together
with the commit — a release without its tag is incomplete.

| Component | Tag format | Example |
| --- | --- | --- |
| FT200 main firmware | `FT200-FW-v<version>` | `FT200-FW-v0.9.0.3` |
| FT200 apploader | `FT200-AL-v<version>` | `FT200-AL-v0.4.9.0` |
| FT200 apploader updater | `FT200-ALU-v<version>` | `FT200-ALU-v0.1.5.0` |
| Device Manager | `FDM-SW-v<version>` | `FDM-SW-v1.42.0.7` |
| Track Director | `FTD-SW-v<version>` | `FTD-SW-v0.95.0.0` |
| Signboard software | `SB-SW-v<version>` | `SB-SW-v1.11.2.0` |

Procedure:

1. Before tagging, list the prior tags for the same component
   (`git tag --list 'FT200-*'`) and match that series exactly.
   Historical outliers exist (`FT-ALU-v0.1.4.0`, the
   `FT200-FW-0.8.x` series without the `v`) — follow the table, not
   the outliers.
2. Create the tag annotated, on the release commit:
   `git tag -a FT200-FW-v<version> <commit> -m ""` (an empty message
   matches the existing series).
3. Push it with the release: `git push origin <tag>`.

These tags are separate from the component tags in `flagging-stm32`
(bare `X.Y.Z.W` for firmware, `AL_vX.Y.Z.W` for apploader). Each repo
tags its own releases; the conventions do not carry across.

History and the 2026-08-14 backfill are recorded in issue #12.
