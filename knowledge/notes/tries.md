---
slug: tries
concept: tries
reviewed: false
---
## Idea
A trie, or prefix tree, stores a set of strings so that strings sharing a beginning share a path. Each node stands for a prefix, each edge adds one character, and a flag on a node says that a stored string ends there. Walking down the tree character by character answers questions about prefixes in time proportional to the length of the query, not the number of stored strings.

## When it applies
Use it when many queries ask whether any stored string begins with a given prefix, when you want to list or count all strings with a prefix, or when you search a grid or text for many words at once and want to stop a path as soon as no word can continue it. A hash set answers exact membership well but cannot answer prefix questions cheaply.

## Common mistakes
- Treating a prefix as if it were a stored word, which needs the end-of-word flag.
- Forgetting to create missing nodes during insertion, or failing to handle missing children during lookup.
- Using fixed-size child arrays without checking the alphabet.
- Spending large amounts of memory when strings share little.
- Rebuilding the structure for every query.

## Socratic questions
- What does a node stand for, and how do you know a word ends there?
- What happens when you look up a prefix that is not the beginning of any stored string?
- How should the children of a node be stored, given the alphabet?
- Do queries ask about whole words, prefixes, or both?
- How much memory does the structure use when strings share few prefixes?

## Tiny illustration
Store "car", "card" and "care". They share the path c, a, r, which is also a word ending, then branch into d and e. Asking whether anything starts with "ca" follows two edges and succeeds. Asking for "cat" follows two edges and then finds no edge for t, so it fails after three steps whatever the collection size.

## Related concepts
string-manipulation, tree-dfs, hash-map-lookup
