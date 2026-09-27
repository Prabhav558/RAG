Feature: The quality gate
  Work is self-appraised, judged independently, and moves on only when it reaches its target.

  Background:
    Given a published scorecard "Spec Quality" requiring 2 judges within 10% and a self-appraisal
    And a project "Apollo" owned by "Pat" with a task "Write requirements" owned by "Alice"

  Scenario: Work is judged only after the owner self-appraises and submits it
    When "Alice" starts a submission for "Write requirements"
    And "Alice" submits it
    Then it is rejected with "S005"
    When "Alice" self-appraises it at 9
    And "Alice" submits it
    Then the submission is "in_review"

  Scenario: Owners cannot judge their own work
    Given "Alice" has submitted "Write requirements"
    When "Alice" judges it at 10
    Then it is rejected with "S003"

  Scenario: Agreeing judges decide, and the official score is their mean
    Given "Alice" has submitted "Write requirements"
    When "Bob" judges it at 9
    And "Carol" judges it at 8
    And "Lead" decides
    Then the decision is "passed" with an official score of 8.5

  Scenario: Disagreeing judges go to adjudication by someone independent
    Given "Alice" has submitted "Write requirements"
    When "Bob" judges it at 9
    And "Carol" judges it at 5
    And "Lead" decides
    Then the submission is "adjudication"
    When "Bob" adjudicates it as "passed" because "I was right"
    Then it is rejected with "S003"
    When "Dana" adjudicates it as "redo" because "Unambiguity guideline was misread by one judge"
    Then the decision is "redo"

  Scenario: Work below target is redone as a new attempt
    Given "Alice" has submitted "Write requirements"
    When "Bob" judges it at 5
    And "Carol" judges it at 5
    And "Lead" decides
    Then the decision is "redo"
    And "Apollo" is "red"
    When "Alice" starts a submission for "Write requirements"
    Then it is attempt 2

  Scenario: A project is green only when everything beneath it is green
    Given the project "Apollo" also has a task "Design" owned by "Alice"
    And "Alice" has submitted "Write requirements"
    When "Bob" judges it at 9
    And "Carol" judges it at 9
    And "Lead" decides
    Then "Write requirements" is "green"
    And "Apollo" is "not_started"
