Feature: Stopping bad foundations and diagnosing reds
  A dark-red foundational artefact stops its project. Repeated reds are diagnosed, not blamed.

  Scenario: A dark-red specification stops the project until it is fixed
    Given a published foundational scorecard "Spec Gate"
    And a published scorecard "Build Quality"
    And a project "Apollo" owned by "Pat" with a task "Spec" owned by "Alice"
    And the project "Apollo" also has a task "Build" owned by "Bob"
    When "Alice" submits "Spec" against "Spec Gate" and it is judged 2
    Then "Apollo" is "blocked"
    When "Bob" starts "Build" against "Build Quality"
    Then it is rejected with "S007"
    When "Alice" submits "Spec" against "Spec Gate" and it is judged 9
    And "Bob" starts "Build" against "Build Quality"
    Then the submission is "open"

  Scenario: Three reds put a person on the attention list until a lead diagnoses them
    Given a published scorecard "Task Quality"
    And "Eve" has had 3 pieces of work judged red against "Task Quality"
    Then "Eve" needs a diagnosis
    When "Eve" records a diagnosis of "skill" with action "train" for "Eve"
    Then it is rejected with "S003"
    When "Lead" records a diagnosis of "skill" with action "train" for "Eve"
    Then "Eve" no longer needs a diagnosis
