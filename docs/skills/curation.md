## Skills Marketplace Curation

Story 4.9 adds an explicit editorial layer to the marketplace so users can
distinguish DeployWhisper-maintained guidance from community skills that passed
extra review.

### Badge meanings

- `Official` means the skill is currently maintained by DeployWhisper. This is
  derived from the manifest maintainer metadata and is intended for first-party
  guidance that DeployWhisper is willing to keep current.
- `Featured` means the skill is community-authored but has passed an editorial
  review by DeployWhisper curators. Featured skills are still community work:
  they must remain community-authored and community-maintained, and the badge
  signals review quality rather than first-party ownership.

### Editorial bar for featured community skills

Curators should only mark a community skill as featured when all of these are
true:

- the manifest is valid and the skill body is specific, deterministic, and
  advisory-first
- the harness suite passes and covers the important trigger and non-match paths
- the skill has a clearly identified maintainer who responds to issues and PR
  feedback
- the guidance is materially useful for a real tool or workflow and does not
  duplicate an existing first-party skill with worse quality
- examples are synthetic and do not include secrets, private infrastructure
  identifiers, or unsafe operational shortcuts

### Review workflow

1. Confirm the manifest metadata is complete, including `author` and, when
   different, `maintainer`.
2. Run `deploywhisper skill lint skills/<skill>.md`.
3. Run `deploywhisper skill test <skill-id>`.
4. Review the markdown for clarity, determinism, and risk coverage.
5. Only then add `featured: true` to the manifest for a curated community
   skill.

### Removal and de-listing process

Curators should remove the `Featured` badge or de-list a skill entirely when one
or more of these conditions hold:

- the harness stops passing and the maintainer does not fix it in a reasonable
  time
- the skill becomes stale after upstream tool changes and produces misleading
  guidance
- the content is duplicated by a better maintained skill and no longer adds
  unique value
- the maintainer abandons the skill or stops responding to security or quality
  issues
- the skill is found to contain unsafe guidance, fabricated claims, or sensitive
  material

Recommended sequence:

1. Open an issue or PR documenting the quality concern.
2. Remove `featured: true` first if the skill still has value but no longer
   meets the editorial bar.
3. Remove the skill from the published catalog if it is abandoned, misleading,
   or unsafe.
4. Keep the change traceable in the PR description so future curators know why
   the badge or skill was removed.
