---
slug: math-number-theory
concept: math-number-theory
reviewed: false
---
## Idea
Many programming problems hide simple arithmetic facts: remainders, divisibility, factors and primes. Recognizing the fact often replaces a long simulation with a short formula or a loop over far fewer values. The tools are modulo arithmetic, greatest common divisor, and the observation that structure repeats.

## When it applies
Reach for these ideas when numbers are large, when a pattern repeats with a fixed period, or when the question concerns divisibility, cycles, digits or counting multiples. Reducing values by a modulus keeps them small, and the greatest common divisor can be computed efficiently by repeated remainders. To test whether a number has a factor, you only need to check candidates up to its square root.

## Common mistakes
- Letting intermediate values overflow in a language with fixed-width integers.
- Forgetting that the remainder of a negative number behaves differently across languages.
- Looping to the number itself when its square root would do.
- Dividing with rounding and expecting exact results.
- Overlooking small special values such as zero, one and two.

## Socratic questions
- What happens to the remainder when you add or multiply, and can you reduce early?
- Does the pattern repeat, and with what period?
- How far do you really need to search for a factor?
- How does this language treat negative operands for division and remainder?
- What do zero and one do to your formula?

## Tiny illustration
You want the last digit of a very large sum of numbers. Rather than adding the full values, keep only the remainder when divided by ten after each addition. The last digit of a sum depends only on the last digits of the parts, so the small remainders give the same answer without ever holding a huge number.

## Related concepts
bit-manipulation, complexity-analysis, edge-case-reasoning
