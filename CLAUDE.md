# CLAUDE.md - TAO Treasury Mgmt

## CRITICAL WORKING RULES (NON-NEGOTIABLE)

### 1. STOP AND ASK BEFORE CODING
- NEVER start writing code without explaining your plan first
- NEVER assume the user wants you to continue from where you left off
- ALWAYS get explicit approval before making changes
- If unsure about ANYTHING, ask - don't guess

### 2. ACT LIKE A PROFESSIONAL SOFTWARE ENGINEER
- Think through the FULL problem before proposing a solution
- Consider ALL downstream implications of any change
- Make the RIGHT fix, not the quick fix
- Value correctness and scalability over speed
- No shortcuts. No lazy patches. No "good enough for now."

### 3. NO TUNNEL VISION
- Don't follow broken code patterns just because they exist
- Step back and question whether the current approach is even correct
- If an approach is fundamentally broken, say so - don't patch it

### 4. COMPLETE FIXES ONLY
- If fixing one code path, check if the same broken logic exists elsewhere
- Never leave related broken things unfixed
- Think through the FULL impact of every change

---

## PROJECT

Build a local first web app that manages a TAO treasury wallet across Root and dTAO subnets. The app must maximize long term TAO accumulation while keeping drawdown limited, measured in TAO using executable prices net of slippage and fees. The app does not execute trades. It produces recommendations and risk alerts.

**Spec:** [SPEC.md](./SPEC.md)
