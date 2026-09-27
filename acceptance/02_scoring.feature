Feature: Scoring against a scorecard
  Scores are computed the same way every time, never rounded up, and always explained.

  Scenario: One factual error fails the assessment even when the average is high
    Given the reference scorecard "Assessment Quality"
    When a judge rates every parameter 8
    And records 1 for the metric "Factual / technical errors in items or keys"
    Then the final score is 7.86
    And the band is "Grey"
    And the evaluation is below target
    And the gate "Technical correctness" fails

  Scenario: A score just below target is never rounded up
    Given a scorecard with KPIs "Content" weighted 99 and "Format" weighted 1 and target 8
    When a judge rates "Content" 8 and "Format" 7
    Then the final score is 7.99
    And the band is "Grey"
    And the evaluation is below target

  Scenario: A measured metric beats the judge's opinion unless overridden with a reason
    Given the reference scorecard "Assessment Quality"
    When a judge rates every parameter 9
    And records 60 for the metric "Objectives covered by at least one item"
    Then "Objective coverage" scores 5 from metrics
    When the judge overrides "Objective coverage" with 9 because "Two objectives are duplicates; real coverage is complete"
    Then "Objective coverage" scores 9 as an override

  Scenario: An optional parameter can be marked not applicable
    Given the reference scorecard "Assessment Quality"
    When a judge rates every parameter 9
    And marks "Accessibility accommodations" as not applicable
    Then the final score is 9
    And the evaluation meets target

  Scenario: Green needs quality AND time AND cost
    Given the reference scorecard "Milestone Delivery Health"
    When a judge rates every parameter 9
    And records that time was met but cost was not
    Then the evaluation meets target
    And QTC is not green
