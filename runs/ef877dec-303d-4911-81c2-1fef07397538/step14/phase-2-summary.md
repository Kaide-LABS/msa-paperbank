# Stage 2

## What was built

The bot's "brain" was separated from the part that talks to WhatsApp. Before, the two were tangled together; now there's a clean middle layer that takes in a message, works out the answer, and sends a reply — without caring which app the message came from. WhatsApp still works exactly as before. Because of this split, a future Microsoft Teams version can be added later without disturbing anything. The way files are labelled in storage was also renamed to remove old Google-specific names, with a documented way to undo it.

## What was decided

The old WhatsApp wiring was kept in place as a safety net rather than deleted, so nothing existing breaks. The storage rename was made reversible, to keep it safe. User experience was left completely unchanged, because this stage was plumbing, not features.

## What is uncertain

Three loose ends were found and are scheduled to be fixed in the next stage: a few places still use the old storage labels and would fail when looking up files, and a planned safety test was not written yet. Also, the full test suite could not be run here due to a software-version mismatch, so final confirmation that everything passes is still pending.
