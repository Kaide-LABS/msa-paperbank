# Stage 1 (final)

## What was built

The bot now hands out past papers as proper, clearly-labelled PDF files with sensible names, so Microsoft Teams opens them correctly instead of treating them as unnamed, unrecognisable files. The bot's search feature also now describes itself fully — its name and every piece of information it uses — so Teams' tool-builder can plug it in without anyone editing by hand. The answers the bot gives are unchanged. New automated checks for all of this now pass.

## What was decided

Names and file labels are cleaned of odd or unsafe characters, falling back to a plain name when needed — to keep files safe and openable. The actual answers were kept exactly the same, so only labels and descriptions changed, not results.

## What is uncertain

This stage is finished and its own checks pass. Two cautions: the work was tested on a slightly different version of the underlying software than the final target, though this is not expected to matter. Also, some unrelated checks elsewhere in the project were already failing before this work and still are — they do not touch these changes, but someone should confirm they're expected.
