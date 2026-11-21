---
slug: string-manipulation
concept: string-manipulation
reviewed: false
---
## Idea
A string is a sequence of characters, and most string problems reduce to scanning it with indices, comparing parts, or building a new one. Because strings are often immutable, repeatedly joining pieces can be slow, and the right approach is usually to collect parts in a list and join once. Many problems are really array problems in disguise.

## When it applies
This covers checking symmetry, comparing rearrangements, splitting and joining, parsing simple formats, and finding or matching substrings. Often the string can be treated with other techniques: two pointers for symmetry checks, counting for rearrangements, a window for substrings, or a table for comparing two strings.

## Common mistakes
- Building a result by repeated concatenation inside a loop.
- Mishandling empty strings and single characters.
- Ignoring case, spaces or punctuation that the problem says to skip.
- Confusing a character with its code or with a one-character string.
- Slicing with ends that are off by one.

## Socratic questions
- What does the string look like for the smallest inputs, including an empty one?
- Which characters are meant to be compared, and which ignored?
- Does the question depend on order, or only on which characters appear?
- Is the string being rebuilt many times, and is there a cheaper way?
- Could a technique from arrays, such as pointers or a window, apply here?

## Tiny illustration
To test whether a phrase reads the same backwards when you ignore spaces and case, first decide what counts: keep only letters and digits, lowercase them. Then place one pointer at the start and one at the end, compare, and move inward until they meet. The cleaning step and the comparing step are separate decisions.

## Related concepts
two-pointers, frequency-counting, tries
