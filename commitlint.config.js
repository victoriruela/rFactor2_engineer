module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [2, 'always', [
      'feat',     // new feature
      'fix',      // bug fix
      'docs',     // documentation only
      'style',    // formatting, no code change
      'refactor', // code change that neither fixes a bug nor adds a feature
      'perf',     // performance improvement
      'test',     // adding or updating tests
      'build',    // build system or external dependencies
      'ci',       // CI/CD configuration
      'chore',    // maintenance, no production code change
      'revert',   // revert a previous commit
      'release',  // version release
    ]],
    'subject-case': [2, 'always', 'lower-case'],
    'header-max-length': [2, 'always', 100],
  },
};
