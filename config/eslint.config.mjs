// The kit's own ESLint config for `kit scan` (writes .audit/scans/lint.json).
// The target's ESLint config is never loaded: config files are code (AGENTS.md rule 2).
// Every rule is a warning; the agents rate consequence, not the linter.
// Plugins resolve from where ESLint itself is installed (`make tools`, ~/audit-tools).
import { createRequire } from "node:module";

const require = createRequire(process.argv[1]);
const regexp = require("eslint-plugin-regexp");

// Core rules (https://eslint.org/docs/latest/rules/), grouped by the kit check they feed.
const rules = {
  // SLOP-SWALLOW: errors hidden or thrown without an Error
  "no-empty": "warn",
  "no-useless-catch": "warn",
  "prefer-promise-reject-errors": "warn",
  "no-throw-literal": "warn",
  // SLOP-DEAD: code nothing reaches or uses
  "no-unused-vars": ["warn", { args: "after-used", caughtErrors: "none" }],
  "no-unreachable": "warn",
  "no-useless-return": "warn",
  "no-unused-private-class-members": "warn",
  // Logic errors
  "no-constant-condition": "warn",
  "no-constant-binary-expression": "warn",
  "no-dupe-else-if": "warn",
  "no-self-compare": "warn",
  "no-unmodified-loop-condition": "warn",
  "consistent-return": "warn",
  eqeqeq: ["warn", "always", { null: "ignore" }],
  // Async mistakes
  "no-await-in-loop": "warn",
  "require-await": "warn",
  "no-async-promise-executor": "warn",
  "no-promise-executor-return": "warn",
  "no-unsafe-finally": "warn",
  // Complexity (SLOP-GOD and the file-review complexity lens); thresholds are review prompts
  complexity: ["warn", 10],
  "max-depth": ["warn", 4],
  "max-lines-per-function": ["warn", { max: 80, skipBlankLines: true, skipComments: true }],
  "max-params": ["warn", 4],
  "max-nested-callbacks": ["warn", 3],
  // Code built from strings (NODE-DANGEROUS-SINK)
  "no-eval": "warn",
  "no-new-func": "warn",
  "no-implied-eval": "warn",
  // SLOP-LEFTOVER
  "no-warning-comments": ["warn", { terms: ["todo", "fixme", "xxx", "hack"], location: "anywhere" }],
  // Regular expressions with super-linear time on crafted input (Node.js "Don't Block the
  // Event Loop"); community plugin https://ota-meshi.github.io/eslint-plugin-regexp/
  "regexp/no-super-linear-backtracking": "warn",
  "regexp/no-super-linear-move": "warn",
};

export default [
  {
    files: ["**/*.js", "**/*.cjs", "**/*.mjs"],
    ignores: ["**/*.min.js"],
    linterOptions: { noInlineConfig: true, reportUnusedDisableDirectives: "off" },
    languageOptions: { ecmaVersion: "latest", sourceType: "commonjs" },
    plugins: { regexp },
    rules,
  },
  {
    files: ["**/*.mjs"],
    languageOptions: { sourceType: "module" },
  },
];
