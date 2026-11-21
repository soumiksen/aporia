---
slug: bst-properties
concept: bst-properties
reviewed: false
---
## Idea
A binary search tree keeps one rule at every node: everything in the left subtree is smaller and everything in the right subtree is larger, according to the chosen treatment of equal values. The rule applies to the whole subtree, not just to the two children. Because of it, an inorder walk visits values in sorted order, and a search can discard half the tree at each step if the tree is balanced.

## When it applies
Use these properties when a question involves ordered values stored in a tree: searching, finding the next larger value, checking validity, or counting values in a range. Often you can prune whole subtrees by comparing against the current node, or rely on the sorted order of an inorder walk instead of doing extra work.

## Common mistakes
- Checking only that a node is between its direct children, which misses violations deeper in the subtree.
- Ignoring the rule for equal values.
- Assuming the tree is balanced, so a search is fast; a skewed tree behaves like a list.
- Updating one link in an insertion or deletion and forgetting to reconnect the rest.
- Passing the wrong bounds down when validating.

## Socratic questions
- What range of values is allowed anywhere in this subtree, not just at the root of it?
- How would those allowed bounds change as you move to a left child, and to a right child?
- What do you know about the order in which an inorder walk visits values?
- How are equal values treated in this tree?
- Does the speed you expect depend on how balanced the tree is?

## Tiny illustration
A node holds 10, with left child 6 and right child 14. If 6 has a right child 12, the tree is invalid even though 12 is larger than 6, because 12 sits in the left subtree of 10 and must be smaller than 10. The check must therefore carry bounds from ancestors, not just compare a node with its parent.

## Related concepts
tree-dfs, binary-search-index, recursion-base-cases
