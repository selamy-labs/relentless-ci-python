# README example execution

`python -m quality.readme_example_main` checks the exact reviewed shell block
under `## Example behavior`, then builds the package and runs its CLI with the
documented input from a temporary copy of the package, lockfiles and README.
It compares the exit status and complete stdout, including the terminal
newline, with the README output claim. Commands use fixed argument arrays with
no shell evaluation and prohibit runtime Python downloads. Missing tools,
failed builds, failed CLI runs and changed documented commands fail the gate.

This is one part of documentation consistency. The candidate does not yet
validate Markdown structure, local links or spelling, and still requires full
mutation and hosted runtime qualification before enrollment in the published
template.
