# Policy provenance

Relentless CI chooses a strict starting policy and records its inspirations.
The numbers are project decisions, not universal laws attributed to authors.

| Policy | Inspiration | Relationship |
| --- | --- | --- |
| At most 399 physical lines per authored file, including comments and blanks | [Angular v19 rule of one](https://v19.angular.dev/style-guide#rule-of-one) recommends files around 400 lines | 399 is this project's stricter operational boundary; Angular does not prescribe the exact physical-count convention here |
| Cyclomatic complexity at most 10 per function | [NIST SP 500-235](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication500-235.pdf), section 2.5, discusses a limit of 10 | Uses the traditional McCabe threshold, with each language analyzer's semantics documented |
| Cognitive complexity at most 5 per function | [Sonar's cognitive-complexity discussion](https://community.sonarsource.com/t/webinar-refactoring-with-cognitive-complexity/45331) describes higher defaults | 5 is deliberately stricter; it is not Sonar's recommended default |
| 100% lines and branches plus every valid mutant killed | Coverage and mutation expose different test weaknesses | This project's adequacy policy; a percentage alone does not prove correctness |

Measure both complexity metrics because they model different costs. A function
can have a low path count but still be difficult to understand. Small focused
functions support review, testing and refactoring; splitting code solely to
manipulate a metric is not remediation.

Mutation evidence must include the actual planned inventory and raw outcomes.
A timeout, tool error, missing report or skipped mutant is not a successful
kill. Security evidence likewise requires complete source and package
inventories, not merely a zero exit status.
