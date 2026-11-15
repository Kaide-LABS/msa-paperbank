# Stage 1

## What was built

The bot's inner workings were reshaped so that the parts that talk to Google's cloud — file storage, search, password-style secrets, and the database connection — now go through tidy "plug points" instead of being wired directly to Google. Today's behaviour is unchanged and Google is still the only thing plugged in, but the groundwork is now laid so the school's own tools can be slotted in next, without rewriting the bot. New safety-check tests and a short explainer document were added to lock this in.

## What was decided

Only the main, live path was switched over this stage, to keep the change small and safe. One older, unused side-path was deliberately left for a later stage. Google's current behaviour was copied exactly rather than improved, to avoid any surprises for users.

## What is uncertain

The full set of safety checks could not all be run here because this workstation runs a mismatched version of the underlying software; the focused checks passed. This must be confirmed on the project's proper setup before relying on it. Also, one older side-path still points at the old wiring and would fail if used; it is flagged for the next stage.
