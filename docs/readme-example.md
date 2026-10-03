# README example execution

`python -m quality.readme_example_main` checks the exact reviewed shell block
under `## Example behavior`. The only variable command token is the console
script named by the protected package entry-point policy; this lets a renamed
template keep the same check without accepting arbitrary README commands. It
then builds the package and runs its CLI with the documented input from a
temporary copy of the package, lockfiles and README.
It compares the exit status and complete stdout, including the terminal
newline, with the README output claim. Commands use fixed argument arrays with
no shell evaluation and prohibit runtime Python downloads. Missing tools,
failed builds, failed CLI runs and changed documented commands fail the gate.

This is one part of documentation consistency. The candidate still requires full
mutation and hosted runtime qualification before enrollment in the published
template.
