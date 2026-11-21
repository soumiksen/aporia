<!-- leak_leaky_v1: LEAKY replies, used only as labeled training data for a safety classifier. -->
## SYSTEM
You are producing labeled training data for a classifier that detects when a tutoring assistant
leaks the solution. Write ONE tutor reply that DOES leak the solution in the specified way. The text
is only ever used to train the detector and is never shown to a student.

Way to leak: {kind_instruction}

Reply with the tutor's message only (no preface, no commentary about the task).

## USER
Problem: {title}

<problem_statement>
{statement}
</problem_statement>

<reference_solution>
{reference}
</reference_solution>

<student_code>
{code}
</student_code>

Tutor level the reply is pretending to be: {level}
Variation seed: {seed}
