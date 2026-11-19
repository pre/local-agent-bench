# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `imagepolicy` command line: print the reason when no tag is selected.

### Fixed

- Order pre-release tags by SemVer 2.0.0 precedence: a release is newer than its release candidates, and `rc.10` is newer than `rc.9`.

## [0.7.0] - 2026-10-14

### Added

- Track `major` for clusters that follow every new release.
- `allow_prerelease` argument of `select_tag` for the staging channel.

### Fixed

- Ignore tags with build metadata when they differ only in the metadata.

## [0.6.2] - 2026-08-03

### Fixed

- Accept tags with a `v` prefix, such as `v1.4.0`.
- Order `1.10.0` after `1.9.0` (the parts were compared as text).

## [0.6.1] - 2026-07-21

### Changed

- `newer_tags` returns the tags oldest first.

### Fixed

- Ignore tags that are not versions, such as `latest` and `sha-5114f85`.

## [0.6.0] - 2026-06-30

### Added

- First version used by the rollout controller.
