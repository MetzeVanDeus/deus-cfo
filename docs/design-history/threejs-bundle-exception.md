# Three.js bundle exception

The Oracle lens remains lazy-loaded behind `React.lazy` and is not part of the initial application interaction path. Its Three.js chunk is intentionally large (approximately 825 KB minified in the audit build), so the release keeps the visual effect only as a non-critical enhancement.

This beta does not refactor the module for line counts or claim the warning is solved. Replacing the effect or splitting its internals is an incremental follow-up only if startup or bundle measurements show a user-visible cost.
