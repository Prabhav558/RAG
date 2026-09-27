Feature: Migrating legacy spreadsheet scorecards
  History comes in without inventing quality, and every difference from the old totals is explained.

  Scenario: A clean legacy workbook reproduces every legacy total
    When the legacy file "code-review-quality.xlsx" is previewed
    Then 15 rating rows would be imported
    And 15 of 15 legacy totals are reproduced

  Scenario: Conflicting duplicate ratings are rejected, not guessed
    When the legacy file "training-session-quality.xlsx" is previewed
    Then rating rows 25 and 26 are rejected with "M04"
    And no difference from the legacy totals is unexplained

  Scenario: A file that is not a scorecard is refused
    When the legacy file "broken-no-header.xlsx" is previewed
    Then the migration fails with "M002"
