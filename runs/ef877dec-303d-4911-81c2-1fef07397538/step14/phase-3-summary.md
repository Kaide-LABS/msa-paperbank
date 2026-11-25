# Stage 3

## What was built

The bot can now store files on the school's own system and hand out download links that work for a short time, then expire — so files stay private without relying on Google. A new rule also makes sure only approved requests can ask the bot for a paper. This replaces parts that previously depended on Google's cloud.

## What was decided

Download links were made to expire quickly and be tamper-proof, for safety. Old Google-specific account details were stripped out of the setup files, so nothing is tied to Google by accident. Where a choice existed, the team favoured settings that keep the system locked-down by default.

## What is uncertain

This stage finished, but with gaps that need attention. The full set of safety checks could not all be run here because of a mismatch in the testing environment — they must be re-run on the school's proper setup before trusting the result. One planned automatic check that guards against leftover Google details was not written yet. And the real before-and-after search comparison still has to be done on the live collection later by an operator.
