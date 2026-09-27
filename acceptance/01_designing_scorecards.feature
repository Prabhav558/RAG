Feature: Designing scorecards
  Anyone can design a scorecard for any subject, but only a complete, unambiguous scorecard can be used.

  Scenario: A scorecard cannot be published without a purpose
    Given a draft scorecard "Proposal Quality" with one fully defined KPI "Clarity"
    And its purpose is empty
    When the designer publishes it
    Then it is rejected with "V016"

  Scenario: Every score on the scale needs a guideline
    Given a draft scorecard "Proposal Quality" with one fully defined KPI "Clarity"
    And the rating matrix of "Clarity" has no guideline for scores 4 to 5
    When the designer publishes it
    Then it is rejected with "V005"

  Scenario: Parameters can be broken down to four levels
    Given the reference scorecard "Assessment Quality"
    Then it has 4 levels of parameters
    And its rated parameters carry 100% of the weight

  Scenario: A published version is frozen; change means a new version
    Given the reference scorecard "Client Email Quality"
    When the designer edits the published version
    Then it is rejected with "E009"
    When the designer creates a new version
    Then version 2 is a draft

  Scenario: A scorecard that requires review is approved by someone else
    Given a draft scorecard "Proposal Quality" with one fully defined KPI "Clarity"
    And the scorecard requires review
    When "Dev" submits it for review
    And "Dev" approves it
    Then it is rejected with "S003"
    When "Rhea" approves it
    Then the scorecard version is "published"
