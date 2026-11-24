/**
 * Entry of the POS bundle. It is loaded as `posawesome.js?v=<build>` and, because its name is
 * fixed, a browser can hold an old copy of it. Everything that matters lives in a normal
 * hashed chunk loaded from here, so the lazy views import their shared code from files whose
 * names change on every build. If shared code lived in this entry instead, a view could be
 * linked to a stale cached copy of it and fail with "is not a function" (or do nothing).
 */
await import("./posawesome.main");
