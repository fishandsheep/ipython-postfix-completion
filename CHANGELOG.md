# Changelog

All notable changes to this project are documented here.

## [0.2.0] - 2026-08-09

### Added

- Smart Tab navigation over Python string and bracket closing tokens.
- Editable `key` placeholder for the built-in `.var` template.
- Runtime configuration for enabling or disabling Smart Tab.
- CI coverage for Python 3.11–3.14 and IPython 9.x.

### Changed

- `.var` now expands `expr.var` to `key = expr` and selects `key`.
- Smart Tab navigation is enabled by default in terminal IPython.
- IPython 10+ is not currently supported.

### Migration from 0.1.x

The `.var` expansion changed from `expr = ` to `key = expr`. Users who
depend on the old cursor position or assignment shape should keep using a
custom template until they migrate.

## [0.1.1] - 2026-07-10

- Added the `.var` and `.await` templates.

## [0.1.0] - 2026-07-05

- Initial release.
