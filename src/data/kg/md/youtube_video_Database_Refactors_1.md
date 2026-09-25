# Database Refactors

**Type:** YouTube Video

Are you struggling with **database migration conflicts** during large-scale refactors? This video explores why legacy and refactor branches often represent incompatible views of the same database and why pointing them at the same development instance is a recipe for disaster.

In this guide, we break down why migration tools fail when histories diverge—explaining that they track the **sequence of operations** and checksums rather than just the final schema shape. We also dive into why common "fixes" like `IF NOT EXISTS` can paper over dangerous schema drift.

**What you will learn:**
*   **The Isolation Model:** How to host multiple independent databases on a single local MySQL server to keep your development environment predictable.
*   **Step-by-Step Setup:** A walkthrough of creating branch-specific databases, granting privileges, and managing environment variables safely.
*   **The Safe Branch-Switching Routine:** A deliberate workflow for stopping applications and using specific Docker flags (`--no-deps`, `--force-recreate`) to ensure environment variables are correctly reloaded.
*   **Verification & Recovery:** How to triple-check that your Git branch, environment variables, and migration logs agree before running any commands, and how to recover if a cross-branch migration occurs.
*   **Converging for Release:** Strategies for merging your refactor, including choosing a canonical history and running **clean-install vs. upgrade tests** to catch different failure classes.

**Key Strategy:** Isolate divergent histories during development, then converge them deliberately before you ever hit production. 

Stop fighting your migration history and start **isolating your databases** for a smoother, safer refactoring experience.
